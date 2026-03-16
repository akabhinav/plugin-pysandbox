"""Async event bus — plugins and engine components communicate via events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()

# Type alias for event handlers
EventHandler = Callable[["SandboxEvent"], Coroutine[Any, Any, None]]


@dataclass
class SandboxEvent:
    """An event emitted during sandbox or plugin lifecycle."""

    sandbox_id: str
    event_type: str  # "plugin.installed", "plugin.removed", "sandbox.paused", etc.
    plugin_id: str | None = None
    plugin_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """In-process async pub/sub. Decouples plugin lifecycle from side effects."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type. Use '*' for all events."""
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: SandboxEvent) -> None:
        """Emit an event to all subscribers. Errors are logged, not raised."""
        specific = self._handlers.get(event.event_type, [])
        wildcard = self._handlers.get("*", [])
        all_handlers = specific + wildcard

        if not all_handlers:
            return

        results = await asyncio.gather(
            *(h(event) for h in all_handlers), return_exceptions=True
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "event_handler_error",
                    event_type=event.event_type,
                    handler=all_handlers[i].__qualname__,
                    error=str(result),
                )

    def clear(self) -> None:
        """Remove all subscriptions — used in tests."""
        self._handlers.clear()
