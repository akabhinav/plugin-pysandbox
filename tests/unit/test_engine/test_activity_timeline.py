"""Tests for Activity Timeline feature."""

import pytest

from pysandbox.engine.activity_timeline import ActivityTimeline


class TestActivityTimeline:
    def test_record_entry(self):
        tl = ActivityTimeline()
        entry = tl.record("sb1", "plugin.installed", "Installed postgres")
        assert entry["sandbox_id"] == "sb1"
        assert entry["event_type"] == "plugin.installed"
        assert entry["description"] == "Installed postgres"
        assert entry["severity"] == "info"
        assert entry["timestamp"]

    def test_record_with_metadata(self):
        tl = ActivityTimeline()
        entry = tl.record("sb1", "test", "test", metadata={"key": "val"}, severity="warning")
        assert entry["metadata"]["key"] == "val"
        assert entry["severity"] == "warning"

    def test_get_timeline_newest_first(self):
        tl = ActivityTimeline()
        tl.record("sb1", "e1", "First")
        tl.record("sb1", "e2", "Second")
        tl.record("sb1", "e3", "Third")
        entries = tl.get_timeline("sb1")
        assert entries[0]["description"] == "Third"
        assert entries[2]["description"] == "First"

    def test_get_timeline_limit(self):
        tl = ActivityTimeline()
        for i in range(10):
            tl.record("sb1", "test", f"Entry {i}")
        entries = tl.get_timeline("sb1", limit=3)
        assert len(entries) == 3

    def test_get_timeline_offset(self):
        tl = ActivityTimeline()
        for i in range(10):
            tl.record("sb1", "test", f"Entry {i}")
        entries = tl.get_timeline("sb1", limit=3, offset=5)
        assert len(entries) == 3

    def test_filter_by_event_type(self):
        tl = ActivityTimeline()
        tl.record("sb1", "plugin.installed", "installed")
        tl.record("sb1", "plugin.removed", "removed")
        tl.record("sb1", "plugin.installed", "installed again")
        entries = tl.get_timeline("sb1", event_type="plugin.installed")
        assert len(entries) == 2

    def test_filter_by_severity(self):
        tl = ActivityTimeline()
        tl.record("sb1", "e1", "info entry", severity="info")
        tl.record("sb1", "e2", "error entry", severity="error")
        tl.record("sb1", "e3", "warning entry", severity="warning")
        entries = tl.get_timeline("sb1", severity="error")
        assert len(entries) == 1
        assert entries[0]["severity"] == "error"

    def test_get_total(self):
        tl = ActivityTimeline()
        tl.record("sb1", "e1", "a")
        tl.record("sb1", "e2", "b")
        assert tl.get_total("sb1") == 2
        assert tl.get_total("sb999") == 0

    def test_clear(self):
        tl = ActivityTimeline()
        tl.record("sb1", "e1", "a")
        tl.clear("sb1")
        assert tl.get_total("sb1") == 0

    def test_max_entries(self):
        tl = ActivityTimeline(max_entries_per_sandbox=5)
        for i in range(10):
            tl.record("sb1", "test", f"Entry {i}")
        assert tl.get_total("sb1") == 5

    def test_separate_sandboxes(self):
        tl = ActivityTimeline()
        tl.record("sb1", "e1", "Sandbox 1")
        tl.record("sb2", "e2", "Sandbox 2")
        assert tl.get_total("sb1") == 1
        assert tl.get_total("sb2") == 1

    @pytest.mark.asyncio
    async def test_on_event_handler(self):
        """Test the event bus subscriber auto-records events."""
        from dataclasses import dataclass, field
        from typing import Any

        @dataclass
        class MockEvent:
            sandbox_id: str = "sb1"
            event_type: str = "plugin.installed"
            plugin_id: str = "postgres"
            plugin_name: str = "postgres"
            data: dict[str, Any] = field(default_factory=dict)

        tl = ActivityTimeline()
        await tl.on_event(MockEvent())
        entries = tl.get_timeline("sb1")
        assert len(entries) == 1
        assert "postgres" in entries[0]["description"]
        assert entries[0]["severity"] == "success"

    @pytest.mark.asyncio
    async def test_on_event_destroyed_severity(self):
        from dataclasses import dataclass, field
        from typing import Any

        @dataclass
        class MockEvent:
            sandbox_id: str = "sb1"
            event_type: str = "sandbox.destroyed"
            plugin_id: str | None = None
            plugin_name: str | None = None
            data: dict[str, Any] = field(default_factory=dict)

        tl = ActivityTimeline()
        await tl.on_event(MockEvent())
        entries = tl.get_timeline("sb1")
        assert entries[0]["severity"] == "warning"
