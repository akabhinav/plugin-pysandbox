"""Activity Timeline — records all sandbox events with timestamps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class ActivityEntry:
    """A single event in the sandbox timeline."""

    id: str
    sandbox_id: str
    timestamp: str
    event_type: str
    description: str
    plugin_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info, warning, error, success


class ActivityTimeline:
    """Thread-safe timeline recorder for sandbox events."""

    def __init__(self, max_entries_per_sandbox: int = 500) -> None:
        self._max = max_entries_per_sandbox
        # sandbox_id → [entries] (newest first)
        self._entries: dict[str, list[dict[str, Any]]] = {}

    def record(
        self,
        sandbox_id: str,
        event_type: str,
        description: str,
        plugin_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> dict[str, Any]:
        """Record an activity event. Returns the created entry."""
        entry = {
            "id": str(uuid4()),
            "sandbox_id": sandbox_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "description": description,
            "plugin_name": plugin_name,
            "metadata": metadata or {},
            "severity": severity,
        }
        entries = self._entries.setdefault(sandbox_id, [])
        entries.insert(0, entry)
        # Trim to max
        if len(entries) > self._max:
            self._entries[sandbox_id] = entries[: self._max]
        return entry

    def get_timeline(
        self,
        sandbox_id: str,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get timeline entries with optional filtering."""
        entries = self._entries.get(sandbox_id, [])
        if event_type:
            entries = [e for e in entries if e["event_type"] == event_type]
        if severity:
            entries = [e for e in entries if e["severity"] == severity]
        return entries[offset: offset + limit]

    def get_total(self, sandbox_id: str) -> int:
        return len(self._entries.get(sandbox_id, []))

    def clear(self, sandbox_id: str) -> None:
        self._entries.pop(sandbox_id, None)

    async def on_event(self, event) -> None:
        """EventBus subscriber — auto-record all sandbox events."""
        desc_map = {
            "sandbox.created": "Sandbox created successfully",
            "sandbox.paused": "Sandbox paused — all containers stopped",
            "sandbox.resumed": "Sandbox resumed — all containers restarted",
            "sandbox.destroyed": "Sandbox destroyed — all resources cleaned up",
            "plugin.installed": f"Plugin '{event.plugin_name}' installed",
            "plugin.removed": f"Plugin '{event.plugin_name}' removed",
        }
        description = desc_map.get(event.event_type, event.event_type)
        severity = "success" if "installed" in event.event_type or "created" in event.event_type else "info"
        if "removed" in event.event_type or "destroyed" in event.event_type:
            severity = "warning"

        self.record(
            sandbox_id=event.sandbox_id,
            event_type=event.event_type,
            description=description,
            plugin_name=event.plugin_name,
            metadata={"plugin_id": event.plugin_id} if event.plugin_id else {},
            severity=severity,
        )
