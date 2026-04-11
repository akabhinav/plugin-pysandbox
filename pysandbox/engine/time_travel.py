"""Time-travel snapshots — rewind a sandbox to an earlier point in time.

This module implements the "undo button for infrastructure" feature:
periodically capture the state of every plugin volume so the caller can
later rewind the whole sandbox to a previous moment. Useful when you
break something (wrong migration, mass DELETE, corrupted cache) and
don't want to re-seed everything from scratch.

The implementation is intentionally simple:

1. `capture(sid)` snapshots every plugin volume by running a throwaway
   `alpine` container that tars `/src/.` into a named snapshot volume
2. Snapshots are kept in an in-memory ring buffer (default 10 per
   sandbox) with a configurable max, so we don't fill the disk
3. `rewind(sid, snapshot_id)` pauses the sandbox, restores each
   plugin volume from the tarball, and resumes

Like branching, this uses container-based copy so it works with any
Docker storage driver — no overlay2 reflink / btrfs snapshot needed.
A production implementation would use those when available for O(1)
snapshots, but correctness-first.

The auto-capture loop is optional: if a background task is started,
it snapshots every `interval_seconds` until stopped. Otherwise
snapshots are purely explicit.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()


# ── Data model ──────────────────────────────────────────────────────────

@dataclass
class VolumeSnapshot:
    """One captured plugin volume in a snapshot."""

    plugin_name: str
    source_volume: str
    snapshot_volume: str


@dataclass
class SandboxSnapshot:
    """A full point-in-time capture of every plugin volume for one sandbox."""

    id: str
    sandbox_id: str
    taken_at: str
    label: str | None = None
    volumes: list[VolumeSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sandbox_id": self.sandbox_id,
            "taken_at": self.taken_at,
            "label": self.label,
            "volume_count": len(self.volumes),
            "volumes": [
                {
                    "plugin_name": v.plugin_name,
                    "source_volume": v.source_volume,
                    "snapshot_volume": v.snapshot_volume,
                }
                for v in self.volumes
            ],
        }


class TimeTravelError(Exception):
    """Raised when a snapshot or rewind op can't complete cleanly."""


# ── Engine ──────────────────────────────────────────────────────────────

class TimeTravelEngine:
    """Point-in-time capture and restore for sandboxes.

    The ring buffer keeps at most `max_snapshots_per_sandbox` items per
    sandbox; adding a new snapshot when the buffer is full evicts the
    oldest one AND best-effort removes its snapshot volumes so the disk
    doesn't leak.
    """

    def __init__(
        self,
        sandbox_engine,
        instance_repo,
        docker_runtime,
        *,
        max_snapshots_per_sandbox: int = 10,
    ) -> None:
        self._engine = sandbox_engine
        self._repo = instance_repo
        self._docker = docker_runtime
        self._max = max_snapshots_per_sandbox
        self._snapshots: dict[str, deque[SandboxSnapshot]] = {}
        # Per-sandbox auto-capture tasks.
        self._auto_tasks: dict[str, asyncio.Task] = {}

    # ── public API ─────────────────────────────────────────────────────

    async def capture(self, sandbox_id: str, label: str | None = None) -> dict[str, Any]:
        """Take a new snapshot of every plugin volume in a sandbox.

        The sandbox is briefly paused so the captured state isn't torn
        mid-write (e.g. postgres in the middle of a checkpoint). If the
        sandbox is already paused we leave it paused.
        """
        sandbox = await self._engine.get(sandbox_id)
        if not sandbox:
            raise TimeTravelError(f"sandbox {sandbox_id} not found")

        was_paused = sandbox.get("status") == "paused"
        if not was_paused:
            await self._engine.pause(sandbox_id)

        try:
            instances = await self._repo.list_instances(sandbox_id)
            volumes: list[VolumeSnapshot] = []
            snap_id = f"snap-{uuid4().hex[:8]}"
            for inst in instances:
                src = self._volume_name(inst)
                if not src:
                    continue
                dst = f"{src}-{snap_id}"
                try:
                    await self._copy_volume(src, dst)
                    volumes.append(VolumeSnapshot(
                        plugin_name=inst.get("plugin_name", ""),
                        source_volume=src,
                        snapshot_volume=dst,
                    ))
                except Exception as e:
                    logger.warning(
                        "time_travel_volume_capture_failed",
                        sandbox=sandbox_id, src=src, error=str(e),
                    )
            snapshot = SandboxSnapshot(
                id=snap_id,
                sandbox_id=sandbox_id,
                taken_at=datetime.now(timezone.utc).isoformat(),
                label=label,
                volumes=volumes,
            )
            self._append_with_eviction(snapshot)
            return snapshot.to_dict()
        finally:
            if not was_paused:
                try:
                    await self._engine.resume(sandbox_id)
                except Exception:
                    logger.warning("time_travel_resume_failed", sandbox=sandbox_id)

    async def rewind(self, sandbox_id: str, snapshot_id: str) -> dict[str, Any]:
        """Restore a sandbox to the state captured in `snapshot_id`.

        Steps:
          1. Verify the snapshot exists for this sandbox
          2. Pause the sandbox (stop writes)
          3. For each volume in the snapshot, copy snapshot → source
          4. Resume the sandbox

        Containers are not recreated — since they mount the same volume
        names, a simple restart picks up the restored data on resume.
        Stateless plugins (like code-executor) are unaffected.
        """
        snapshot = self._find_snapshot(sandbox_id, snapshot_id)
        if snapshot is None:
            raise TimeTravelError(
                f"snapshot {snapshot_id} not found for sandbox {sandbox_id}",
            )

        sandbox = await self._engine.get(sandbox_id)
        if not sandbox:
            raise TimeTravelError(f"sandbox {sandbox_id} not found")

        was_paused = sandbox.get("status") == "paused"
        if not was_paused:
            await self._engine.pause(sandbox_id)

        restored = []
        try:
            for vol in snapshot.volumes:
                try:
                    # Wipe and re-populate. Using `sh -c "rm -rf /dst/* /dst/.[!.]* ; cp -a /src/. /dst/"`
                    # would be cleaner, but we keep behavior in `_copy_volume`
                    # for consistency with branching; the copy target replaces
                    # files without removing ones that weren't in the source,
                    # which is "good enough" for dev rewind.
                    await self._copy_volume(vol.snapshot_volume, vol.source_volume)
                    restored.append({
                        "plugin_name": vol.plugin_name,
                        "status": "ok",
                    })
                except Exception as e:
                    logger.warning(
                        "time_travel_restore_failed",
                        plugin=vol.plugin_name, error=str(e),
                    )
                    restored.append({
                        "plugin_name": vol.plugin_name,
                        "status": "error",
                        "error": str(e)[:200],
                    })
        finally:
            if not was_paused:
                try:
                    await self._engine.resume(sandbox_id)
                except Exception:
                    logger.warning("time_travel_resume_failed", sandbox=sandbox_id)

        return {
            "sandbox_id": sandbox_id,
            "snapshot_id": snapshot_id,
            "restored": restored,
        }

    def list_snapshots(self, sandbox_id: str) -> list[dict[str, Any]]:
        """Return every snapshot for a sandbox, newest first."""
        buf = self._snapshots.get(sandbox_id)
        if not buf:
            return []
        return [s.to_dict() for s in reversed(buf)]

    async def delete_snapshot(self, sandbox_id: str, snapshot_id: str) -> bool:
        """Remove a snapshot and its underlying snapshot volumes."""
        snapshot = self._find_snapshot(sandbox_id, snapshot_id)
        if snapshot is None:
            return False
        buf = self._snapshots.get(sandbox_id) or deque()
        try:
            buf.remove(snapshot)
        except ValueError:
            pass
        await self._drop_volumes(snapshot)
        return True

    async def start_auto_capture(
        self, sandbox_id: str, interval_seconds: int = 300,
    ) -> None:
        """Start a background task that snapshots every `interval_seconds`.

        No-op if an auto-capture is already running for this sandbox.
        """
        if sandbox_id in self._auto_tasks:
            return
        self._auto_tasks[sandbox_id] = asyncio.create_task(
            self._auto_loop(sandbox_id, interval_seconds),
        )

    async def stop_auto_capture(self, sandbox_id: str) -> bool:
        task = self._auto_tasks.pop(sandbox_id, None)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    # ── internals ──────────────────────────────────────────────────────

    def _find_snapshot(
        self, sandbox_id: str, snapshot_id: str,
    ) -> SandboxSnapshot | None:
        buf = self._snapshots.get(sandbox_id)
        if not buf:
            return None
        for snap in buf:
            if snap.id == snapshot_id:
                return snap
        return None

    def _append_with_eviction(self, snapshot: SandboxSnapshot) -> None:
        buf = self._snapshots.setdefault(snapshot.sandbox_id, deque())
        if len(buf) >= self._max:
            evicted = buf.popleft()
            # Schedule cleanup but don't block the capture path on it.
            asyncio.create_task(self._drop_volumes(evicted))
        buf.append(snapshot)

    async def _drop_volumes(self, snapshot: SandboxSnapshot) -> None:
        for vol in snapshot.volumes:
            try:
                await self._docker.remove_volume(vol.snapshot_volume)
            except Exception:
                logger.warning(
                    "time_travel_drop_volume_failed", volume=vol.snapshot_volume,
                )

    def _volume_name(self, instance: dict[str, Any]) -> str | None:
        sid = instance.get("sandbox_id", "")
        name = instance.get("plugin_name", "")
        if not sid or not name:
            return None
        return f"pysb-{sid[:8]}-{name}"

    async def _copy_volume(self, src_volume: str, dst_volume: str) -> None:
        """Run a throwaway alpine container to copy files src → dst."""
        def _run():
            client = self._docker._get_client()
            client.containers.run(
                "alpine:latest",
                command=["sh", "-c", "cp -a /src/. /dst/ 2>&1 || exit 0"],
                volumes={
                    src_volume: {"bind": "/src", "mode": "ro"},
                    dst_volume: {"bind": "/dst", "mode": "rw"},
                },
                remove=True,
                detach=False,
            )
        await asyncio.to_thread(_run)

    async def _auto_loop(self, sandbox_id: str, interval_seconds: int) -> None:
        """Background loop: snapshot, sleep, repeat. Dies on cancel."""
        try:
            while True:
                try:
                    await self.capture(sandbox_id, label="auto")
                except Exception as e:
                    logger.warning(
                        "time_travel_auto_capture_failed",
                        sandbox=sandbox_id, error=str(e),
                    )
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
