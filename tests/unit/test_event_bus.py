"""Tests for the async event bus."""

import pytest

from pysandbox.engine.event_bus import EventBus, SandboxEvent


@pytest.fixture
def bus():
    return EventBus()


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self, bus):
        """Events reach subscribed handlers."""
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        event = SandboxEvent(sandbox_id="sb1", event_type="test.event")
        await bus.emit(event)

        assert len(received) == 1
        assert received[0].sandbox_id == "sb1"

    @pytest.mark.asyncio
    async def test_wildcard_subscriber(self, bus):
        """Wildcard '*' handler receives all events."""
        received = []

        async def handler(event):
            received.append(event.event_type)

        bus.subscribe("*", handler)
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="a"))
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="b"))

        assert received == ["a", "b"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Unsubscribed handlers don't receive events."""
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="test"))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_break_others(self, bus):
        """One handler failing doesn't prevent others from running."""
        results = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            results.append("ok")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="test"))

        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_no_subscribers(self, bus):
        """Emitting with no subscribers doesn't error."""
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="nobody.listens"))

    @pytest.mark.asyncio
    async def test_event_data(self, bus):
        """Event data is passed through correctly."""
        received = []

        async def handler(event):
            received.append(event.data)

        bus.subscribe("test", handler)
        await bus.emit(SandboxEvent(
            sandbox_id="sb1",
            event_type="test",
            data={"key": "value"},
        ))

        assert received[0] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_clear(self, bus):
        """Clear removes all subscriptions."""
        async def handler(event):
            pass

        bus.subscribe("a", handler)
        bus.subscribe("b", handler)
        bus.clear()

        # No error, just no handlers
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="a"))

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self, bus):
        """Multiple handlers on the same event type all fire."""
        results = []

        async def h1(event): results.append("h1")
        async def h2(event): results.append("h2")
        async def h3(event): results.append("h3")

        bus.subscribe("test", h1)
        bus.subscribe("test", h2)
        bus.subscribe("test", h3)
        await bus.emit(SandboxEvent(sandbox_id="sb1", event_type="test"))

        assert set(results) == {"h1", "h2", "h3"}
