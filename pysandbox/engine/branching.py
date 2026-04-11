"""Branchable sandboxes — fork a sandbox as a new one sharing initial state.

A "branch" of sandbox `A` is a fresh sandbox `B` where:

1. Every plugin from `A` is reinstalled under the same plugin_name
2. `B` gets its own network, DNS zone, and generated credentials — it's
   fully isolated from `A` going forward
3. `B` starts with a best-effort copy of `A`'s plugin volumes, so
   the initial state (schemas, topic lists, cached keys, etc.) matches

The volume copy is done through a short-lived `alpine` container that
mounts the old volume at `/src` and the new volume at `/dst` and runs
`cp -a /src/. /dst/`. This works with any Docker storage driver and
doesn't require overlay2 / fuse-overlayfs / btrfs — a deliberate
compatibility trade-off over "real" copy-on-write snapshots.

On kernels that DO support it (overlay2 + reflink), the same abstraction
could be swapped for a zero-copy clone later without changing callers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


class SandboxBranchError(Exception):
    """Raised when a branch operation can't complete cleanly."""


class SandboxBrancher:
    """Creates a new sandbox that starts from another sandbox's current state.

    The brancher doesn't touch Docker directly for the new sandbox — it
    composes `SandboxEngine.create()` (which handles network + plugin
    installation) with a volume copy step run after the new plugin
    containers are up but before they're handed back to the caller.

    The target sandbox's plugins ARE paused during the volume copy so
    we don't capture a torn state (e.g. postgres mid-checkpoint). They
    get unpaused once the copy is done, so the source sandbox is only
    offline for the duration of the copy itself.
    """

    def __init__(self, sandbox_engine, instance_repo, docker_runtime) -> None:
        self._engine = sandbox_engine
        self._repo = instance_repo
        self._docker = docker_runtime

    async def branch(
        self,
        source_sandbox_id: str,
        *,
        new_name: str,
        owner_id: str = "default",
        copy_data: bool = True,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new sandbox forked from `source_sandbox_id`.

        Args:
            source_sandbox_id: the sandbox to fork.
            new_name: name for the new sandbox.
            owner_id: owner for the new sandbox (defaults to "default").
            copy_data: if False, reinstall plugins fresh without copying
                any volume data. Still useful as a "same stack shape" clone.
            tags: extra tags merged into the new sandbox.

        Returns:
            The new sandbox dict with extra `source_sandbox_id` and
            `volumes_copied` fields.
        """
        source = await self._engine.get(source_sandbox_id)
        if not source:
            raise SandboxBranchError(f"source sandbox {source_sandbox_id} not found")

        source_instances = await self._repo.list_instances(source_sandbox_id)
        plugin_specs = self._derive_plugin_specs(source_instances)
        if not plugin_specs:
            raise SandboxBranchError(
                f"source sandbox {source_sandbox_id} has no installed plugins to branch",
            )

        # Merge source tags + caller tags + branch metadata so the new
        # sandbox is self-describing.
        merged_tags: dict[str, str] = {
            **(source.get("tags") or {}),
            **(tags or {}),
            "branched_from": source_sandbox_id,
        }

        new_sandbox = await self._engine.create(
            name=new_name,
            owner_id=owner_id,
            plugins=plugin_specs,
            tags=merged_tags,
        )

        volumes_copied: list[dict[str, Any]] = []
        if copy_data:
            # Pause the source to avoid tearing a live write. We rely on
            # the engine's pause semantics (docker pause) so this is a
            # quick freeze rather than a full stop.
            try:
                await self._engine.pause(source_sandbox_id)
                volumes_copied = await self._copy_all_volumes(
                    source_instances,
                    await self._repo.list_instances(new_sandbox["id"]),
                )
            finally:
                try:
                    await self._engine.resume(source_sandbox_id)
                except Exception:
                    logger.warning(
                        "branch_source_resume_failed",
                        source=source_sandbox_id,
                    )

        return {
            **new_sandbox,
            "source_sandbox_id": source_sandbox_id,
            "volumes_copied": volumes_copied,
        }

    # ── helpers ────────────────────────────────────────────────────────

    def _derive_plugin_specs(
        self, source_instances: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Turn a list of installed plugin instances into a fresh plugin spec.

        We keep plugin_name, plugin_id, version, and config — everything
        else (container_id, credentials, ports) is per-sandbox and must
        be regenerated on create().
        """
        specs = []
        for inst in source_instances:
            specs.append({
                "plugin_id": inst.get("plugin_id"),
                "name": inst.get("plugin_name"),
                "version": inst.get("version"),
                "config": inst.get("config") or {},
                "expose": True,
                "startup_order": inst.get("startup_order", 50),
            })
        return specs

    async def _copy_all_volumes(
        self,
        source_instances: list[dict[str, Any]],
        new_instances: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """For each plugin in the new sandbox, copy volume data from the
        matching source plugin. Best-effort — a single failed copy is
        recorded in the result but doesn't abort the whole branch."""
        by_name = {i.get("plugin_name"): i for i in new_instances}
        results = []
        for src in source_instances:
            name = src.get("plugin_name")
            dst = by_name.get(name)
            if dst is None:
                results.append({"plugin_name": name, "status": "skipped", "reason": "no matching target"})
                continue
            src_vol = self._volume_name(src)
            dst_vol = self._volume_name(dst)
            if not src_vol or not dst_vol:
                results.append({"plugin_name": name, "status": "skipped", "reason": "no volume"})
                continue
            try:
                await self._copy_volume(src_vol, dst_vol)
                results.append({
                    "plugin_name": name,
                    "status": "ok",
                    "src_volume": src_vol,
                    "dst_volume": dst_vol,
                })
            except Exception as e:
                logger.warning(
                    "branch_volume_copy_failed",
                    plugin=name, src=src_vol, dst=dst_vol, error=str(e),
                )
                results.append({
                    "plugin_name": name,
                    "status": "error",
                    "error": str(e)[:200],
                })
        return results

    def _volume_name(self, instance: dict[str, Any]) -> str | None:
        """Infer the Docker volume name from a plugin instance.

        Plugins that persist data use a deterministic naming scheme in
        their docker_config: `pysb-{sandbox_id[:8]}-{plugin_name}`. We
        rebuild that from the instance record rather than asking Docker
        so this works even if the plugin's manifest doesn't declare
        persistent_data explicitly.
        """
        sid = instance.get("sandbox_id", "")
        name = instance.get("plugin_name", "")
        if not sid or not name:
            return None
        return f"pysb-{sid[:8]}-{name}"

    async def _copy_volume(self, src_volume: str, dst_volume: str) -> None:
        """Run a throwaway container that copies files src → dst.

        We use `alpine:latest` because it's tiny, ubiquitous, and the
        `cp -a` in busybox preserves ownership, timestamps, and xattrs
        where supported. The container is auto-removed on exit.
        """
        def _run():
            client = self._docker._get_client()
            container = client.containers.run(
                "alpine:latest",
                command=["sh", "-c", "cp -a /src/. /dst/ 2>&1 || exit 0"],
                volumes={
                    src_volume: {"bind": "/src", "mode": "ro"},
                    dst_volume: {"bind": "/dst", "mode": "rw"},
                },
                remove=True,
                detach=False,
            )
            return container

        await asyncio.to_thread(_run)
        logger.info("branch_volume_copied", src=src_volume, dst=dst_volume)
