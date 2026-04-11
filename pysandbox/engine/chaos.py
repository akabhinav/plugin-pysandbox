"""Chaos Toolkit — inject failures into a running sandbox.

pysandbox already owns every container in the sandbox, so we can inject
a wide range of failures without needing Toxiproxy, Pumba, or any other
external tool. The primitives we expose are intentionally narrow:

- `kill`: SIGKILL a plugin container (optionally scheduled N seconds later)
- `pause`: `docker pause` / `docker unpause` — freezes the process
- `latency`: add egress latency via `tc qdisc` inside the container
- `loss`: drop a % of egress packets
- `cpu_throttle`: `docker update --cpus` to limit to a fraction of a vCPU
- `mem_throttle`: `docker update --memory` to squeeze the container
- `reset`: undo all chaos on a sandbox in one call

Each injection is recorded in a per-sandbox registry so a later `reset`
can roll back cleanly. The registry is in-memory — good enough for
development chaos, not a replacement for a fault-injection platform.

None of these methods require cooperation from the plugin itself, which
is the whole point: you're testing how your app *reacts* to infra failures,
not how the infra chooses to simulate them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ChaosInjection:
    """One active chaos effect on a plugin container."""

    id: str
    sandbox_id: str
    plugin_name: str
    container_id: str
    fault_type: str
    params: dict[str, Any]
    started_at: str
    scheduled_for: str | None = None  # ISO string if delayed


@dataclass
class ChaosRegistry:
    """In-memory list of active chaos injections per sandbox.

    Used so a `reset` call can find every effect to roll back, and so
    `list_active` can show users what's going on.
    """

    by_sandbox: dict[str, list[ChaosInjection]] = field(default_factory=dict)

    def add(self, injection: ChaosInjection) -> None:
        self.by_sandbox.setdefault(injection.sandbox_id, []).append(injection)

    def remove(self, sandbox_id: str, injection_id: str) -> ChaosInjection | None:
        items = self.by_sandbox.get(sandbox_id, [])
        for i, inj in enumerate(items):
            if inj.id == injection_id:
                return items.pop(i)
        return None

    def list_for(self, sandbox_id: str) -> list[ChaosInjection]:
        return list(self.by_sandbox.get(sandbox_id, []))

    def drain(self, sandbox_id: str) -> list[ChaosInjection]:
        return self.by_sandbox.pop(sandbox_id, [])


class ChaosEngine:
    """High-level chaos operations. All methods are async and idempotent-ish."""

    def __init__(self, docker_runtime, instance_repo) -> None:
        self._docker = docker_runtime
        self._repo = instance_repo
        self._registry = ChaosRegistry()
        self._counter = 0

    # ── public API ─────────────────────────────────────────────────────

    async def list_active(self, sandbox_id: str) -> list[dict[str, Any]]:
        """Return all active chaos effects on a sandbox as JSON-serializable dicts."""
        return [self._to_dict(inj) for inj in self._registry.list_for(sandbox_id)]

    async def kill(
        self,
        sandbox_id: str,
        plugin_name: str,
        *,
        after_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """SIGKILL a plugin container, optionally delayed.

        Note: we don't remove the container — a restart_policy container
        may come back up on its own, which is usually what you want to
        test ("does my retry loop survive a flap?").
        """
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]

        async def _do_kill():
            if after_seconds > 0:
                await asyncio.sleep(after_seconds)
            await self._docker.stop(cid, timeout=0)
            logger.info("chaos_kill", container=cid[:12], plugin=plugin_name)

        injection = self._new_injection(
            sandbox_id, plugin_name, cid, "kill",
            {"after_seconds": after_seconds},
            scheduled=after_seconds > 0,
        )
        self._registry.add(injection)

        if after_seconds > 0:
            # Fire-and-forget: the caller just wants to schedule it.
            asyncio.create_task(_do_kill())
        else:
            await _do_kill()
        return self._to_dict(injection)

    async def pause(self, sandbox_id: str, plugin_name: str) -> dict[str, Any]:
        """Freeze a container with `docker pause`. Processes are suspended."""
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        await self._docker_cmd(cid, "pause")
        injection = self._new_injection(sandbox_id, plugin_name, cid, "pause", {})
        self._registry.add(injection)
        return self._to_dict(injection)

    async def unpause(self, sandbox_id: str, plugin_name: str) -> dict[str, Any]:
        """Unfreeze a container. Looks for and removes any matching `pause` injection."""
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        await self._docker_cmd(cid, "unpause")
        removed = self._remove_by_type(sandbox_id, plugin_name, "pause")
        return {"removed": removed, "plugin_name": plugin_name}

    async def latency(
        self,
        sandbox_id: str,
        plugin_name: str,
        *,
        delay_ms: int,
        jitter_ms: int = 0,
    ) -> dict[str, Any]:
        """Add egress latency to a container using `tc qdisc`.

        The container needs the `iproute2` package (the `tc` binary).
        Most production images ship it; for alpine-only images the effect
        will return an error and we surface it rather than silently no-op.
        """
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        jitter_clause = f" {jitter_ms}ms distribution normal" if jitter_ms else ""
        cmd = (
            "tc qdisc del dev eth0 root 2>/dev/null; "
            f"tc qdisc add dev eth0 root netem delay {delay_ms}ms{jitter_clause}"
        )
        output = await self._docker.exec_in_container(cid, cmd)
        injection = self._new_injection(
            sandbox_id, plugin_name, cid, "latency",
            {"delay_ms": delay_ms, "jitter_ms": jitter_ms},
        )
        self._registry.add(injection)
        return {**self._to_dict(injection), "output": output}

    async def packet_loss(
        self,
        sandbox_id: str,
        plugin_name: str,
        *,
        loss_percent: float,
    ) -> dict[str, Any]:
        """Drop a % of egress packets to simulate a flaky network."""
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        cmd = (
            "tc qdisc del dev eth0 root 2>/dev/null; "
            f"tc qdisc add dev eth0 root netem loss {loss_percent}%"
        )
        output = await self._docker.exec_in_container(cid, cmd)
        injection = self._new_injection(
            sandbox_id, plugin_name, cid, "loss",
            {"loss_percent": loss_percent},
        )
        self._registry.add(injection)
        return {**self._to_dict(injection), "output": output}

    async def cpu_throttle(
        self,
        sandbox_id: str,
        plugin_name: str,
        *,
        cpus: float,
    ) -> dict[str, Any]:
        """Limit the container to a fraction of a vCPU via `docker update`."""
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        await self._docker_update(cid, nano_cpus=int(cpus * 1e9))
        injection = self._new_injection(
            sandbox_id, plugin_name, cid, "cpu_throttle", {"cpus": cpus},
        )
        self._registry.add(injection)
        return self._to_dict(injection)

    async def memory_throttle(
        self,
        sandbox_id: str,
        plugin_name: str,
        *,
        memory_mb: int,
    ) -> dict[str, Any]:
        """Shrink container memory limit. Useful for testing OOM behavior."""
        inst = await self._resolve_instance(sandbox_id, plugin_name)
        cid = inst["container_id"]
        await self._docker_update(cid, mem_limit=memory_mb * 1024 * 1024)
        injection = self._new_injection(
            sandbox_id, plugin_name, cid, "mem_throttle", {"memory_mb": memory_mb},
        )
        self._registry.add(injection)
        return self._to_dict(injection)

    async def reset(self, sandbox_id: str) -> dict[str, Any]:
        """Roll back every active chaos effect on a sandbox.

        For each injection we run the inverse: unpause containers, clear
        tc qdiscs, and restore the original CPU/memory limits (approximate —
        we bump back to very generous values rather than remembering the
        originals, which is fine for a dev sandbox).
        """
        injections = self._registry.drain(sandbox_id)
        errors = []
        for inj in injections:
            try:
                await self._undo(inj)
            except Exception as e:
                errors.append({"injection_id": inj.id, "error": str(e)})
        return {
            "sandbox_id": sandbox_id,
            "reset_count": len(injections),
            "errors": errors,
        }

    # ── internals ──────────────────────────────────────────────────────

    async def _resolve_instance(self, sandbox_id: str, plugin_name: str) -> dict[str, Any]:
        inst = await self._repo.get_instance(sandbox_id, plugin_name)
        if not inst:
            raise ValueError(f"Plugin '{plugin_name}' not found in sandbox {sandbox_id}")
        if not inst.get("container_id"):
            raise ValueError(f"Plugin '{plugin_name}' has no container to inject into")
        return inst

    def _new_injection(
        self,
        sandbox_id: str,
        plugin_name: str,
        container_id: str,
        fault_type: str,
        params: dict[str, Any],
        *,
        scheduled: bool = False,
    ) -> ChaosInjection:
        self._counter += 1
        now = datetime.now(timezone.utc).isoformat()
        return ChaosInjection(
            id=f"chaos-{self._counter}",
            sandbox_id=sandbox_id,
            plugin_name=plugin_name,
            container_id=container_id,
            fault_type=fault_type,
            params=params,
            started_at=now,
            scheduled_for=now if scheduled else None,
        )

    def _to_dict(self, inj: ChaosInjection) -> dict[str, Any]:
        return {
            "id": inj.id,
            "sandbox_id": inj.sandbox_id,
            "plugin_name": inj.plugin_name,
            "container_id": inj.container_id[:12],
            "fault_type": inj.fault_type,
            "params": inj.params,
            "started_at": inj.started_at,
            "scheduled_for": inj.scheduled_for,
        }

    def _remove_by_type(
        self, sandbox_id: str, plugin_name: str, fault_type: str
    ) -> list[dict[str, Any]]:
        """Pop matching injections from the registry. Used by undo paths."""
        removed = []
        items = self._registry.by_sandbox.get(sandbox_id, [])
        keep = []
        for inj in items:
            if inj.plugin_name == plugin_name and inj.fault_type == fault_type:
                removed.append(self._to_dict(inj))
            else:
                keep.append(inj)
        self._registry.by_sandbox[sandbox_id] = keep
        return removed

    async def _undo(self, inj: ChaosInjection) -> None:
        """Best-effort reversal for a single injection."""
        if inj.fault_type == "pause":
            await self._docker_cmd(inj.container_id, "unpause")
        elif inj.fault_type in ("latency", "loss"):
            await self._docker.exec_in_container(
                inj.container_id, "tc qdisc del dev eth0 root 2>/dev/null || true",
            )
        elif inj.fault_type == "cpu_throttle":
            # Restore to an unlimited default.
            await self._docker_update(inj.container_id, nano_cpus=0)
        elif inj.fault_type == "mem_throttle":
            # Docker doesn't actually support removing memory limits at
            # runtime; the closest we can get is raising them very high.
            await self._docker_update(inj.container_id, mem_limit=16 * 1024 * 1024 * 1024)
        elif inj.fault_type == "kill":
            # Nothing to undo — the container is gone or has restarted.
            pass

    # Raw docker-py passthroughs. Kept here (not in DockerRuntime) because
    # they're chaos-specific and we don't want to pollute the core runtime
    # surface with every niche control we need.
    async def _docker_cmd(self, container_id: str, verb: str) -> None:
        def _run():
            client = self._docker._get_client()
            container = client.containers.get(container_id)
            getattr(container, verb)()
        await asyncio.to_thread(_run)

    async def _docker_update(self, container_id: str, **kwargs) -> None:
        def _run():
            client = self._docker._get_client()
            container = client.containers.get(container_id)
            container.update(**kwargs)
        await asyncio.to_thread(_run)
