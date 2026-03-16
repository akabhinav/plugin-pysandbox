"""Continuous health monitoring for installed plugins."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pysandbox.engine.event_bus import SandboxEvent
    from pysandbox.runtime.docker_runtime import DockerRuntime

logger = structlog.get_logger()


class HealthMonitor:
    """Periodically probes plugin containers. Updates status on failure."""

    def __init__(self, docker_runtime: "DockerRuntime") -> None:
        self._docker = docker_runtime
        # sandbox_id → {plugin_name → asyncio.Task}
        self._tasks: dict[str, dict[str, asyncio.Task]] = {}

    async def on_plugin_installed(self, event: "SandboxEvent") -> None:
        if event.event_type != "plugin.installed":
            return
        container_id = event.data.get("container_id")
        interval = event.data.get("health_interval", 15)
        if container_id:
            self._start_probe(event.sandbox_id, event.plugin_name or "", container_id, interval)

    async def on_plugin_removed(self, event: "SandboxEvent") -> None:
        if event.event_type != "plugin.removed":
            return
        self._stop_probe(event.sandbox_id, event.plugin_name or "")

    def _start_probe(
        self, sandbox_id: str, plugin_name: str, container_id: str, interval: int
    ) -> None:
        task = asyncio.create_task(
            self._probe_loop(sandbox_id, plugin_name, container_id, interval)
        )
        self._tasks.setdefault(sandbox_id, {})[plugin_name] = task

    def _stop_probe(self, sandbox_id: str, plugin_name: str) -> None:
        tasks = self._tasks.get(sandbox_id, {})
        task = tasks.pop(plugin_name, None)
        if task:
            task.cancel()
        if not tasks:
            self._tasks.pop(sandbox_id, None)

    async def _probe_loop(
        self, sandbox_id: str, plugin_name: str, container_id: str, interval: int
    ) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                healthy = await self._docker.is_healthy(container_id)
                if not healthy:
                    logger.warning(
                        "plugin_unhealthy",
                        sandbox_id=sandbox_id,
                        plugin=plugin_name,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("health_probe_error", plugin=plugin_name)

    async def stop_all(self) -> None:
        """Stop all probes — called on shutdown."""
        for sandbox_tasks in self._tasks.values():
            for task in sandbox_tasks.values():
                task.cancel()
        self._tasks.clear()
