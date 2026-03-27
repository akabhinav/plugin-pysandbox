"""Sandbox TTL & Auto-Cleanup — automatic sandbox destruction after expiry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pysandbox.engine.sandbox_engine import SandboxEngine

logger = structlog.get_logger()


class SandboxTTLManager:
    """Manages time-to-live for sandboxes. Auto-destroys expired sandboxes."""

    def __init__(self) -> None:
        # sandbox_id → {"ttl_seconds": int, "created_at": str, "expires_at": str}
        self._ttls: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._engine: SandboxEngine | None = None

    def set_engine(self, engine: "SandboxEngine") -> None:
        self._engine = engine

    def set_ttl(self, sandbox_id: str, ttl_seconds: int) -> dict[str, Any]:
        """Set or update TTL for a sandbox. Returns TTL info."""
        now = datetime.now(timezone.utc)
        expires = datetime.fromtimestamp(
            now.timestamp() + ttl_seconds, tz=timezone.utc
        )
        info = {
            "sandbox_id": sandbox_id,
            "ttl_seconds": ttl_seconds,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        self._ttls[sandbox_id] = info
        logger.info("ttl_set", sandbox_id=sandbox_id, ttl=ttl_seconds, expires=expires.isoformat())
        return info

    def get_ttl(self, sandbox_id: str) -> dict[str, Any] | None:
        info = self._ttls.get(sandbox_id)
        if not info:
            return None
        # Add remaining time
        expires = datetime.fromisoformat(info["expires_at"])
        remaining = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
        return {**info, "remaining_seconds": remaining}

    def remove_ttl(self, sandbox_id: str) -> bool:
        return self._ttls.pop(sandbox_id, None) is not None

    def list_ttls(self) -> list[dict[str, Any]]:
        """List all TTLs with remaining time."""
        result = []
        now = datetime.now(timezone.utc)
        for sid, info in self._ttls.items():
            expires = datetime.fromisoformat(info["expires_at"])
            remaining = max(0, int((expires - now).total_seconds()))
            result.append({**info, "remaining_seconds": remaining})
        return result

    def get_expired(self) -> list[str]:
        """Get sandbox IDs that have expired."""
        now = datetime.now(timezone.utc)
        expired = []
        for sid, info in self._ttls.items():
            expires = datetime.fromisoformat(info["expires_at"])
            if now >= expires:
                expired.append(sid)
        return expired

    async def start(self) -> None:
        """Start the background TTL checker."""
        if self._task is None:
            self._task = asyncio.create_task(self._check_loop())
            logger.info("ttl_manager_started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _check_loop(self) -> None:
        """Periodically check for expired sandboxes."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                expired = self.get_expired()
                for sid in expired:
                    logger.info("ttl_expired_destroying", sandbox_id=sid)
                    try:
                        if self._engine:
                            await self._engine.destroy(sid)
                        self._ttls.pop(sid, None)
                        logger.info("ttl_sandbox_destroyed", sandbox_id=sid)
                    except Exception as e:
                        logger.error("ttl_destroy_failed", sandbox_id=sid, error=str(e))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ttl_check_error")
