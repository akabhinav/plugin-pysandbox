"""Audit logging for sandbox operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger("audit")


class AuditLog:
    """Structured audit trail for all sandbox operations."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def log(
        self,
        action: str,
        sandbox_id: str,
        actor: str = "system",
        plugin_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "sandbox_id": sandbox_id,
            "actor": actor,
            "plugin_id": plugin_id,
            "details": details or {},
        }
        self._entries.append(entry)
        logger.info("audit", **entry)

    def get_entries(self, sandbox_id: str | None = None) -> list[dict[str, Any]]:
        if sandbox_id:
            return [e for e in self._entries if e["sandbox_id"] == sandbox_id]
        return list(self._entries)
