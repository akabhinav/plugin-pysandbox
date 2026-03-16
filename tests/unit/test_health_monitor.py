"""Tests for the health monitor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.event_bus import SandboxEvent
from pysandbox.engine.health_monitor import HealthMonitor


@pytest.fixture
def mock_docker():
    docker = MagicMock()
    docker.is_healthy = AsyncMock(return_value=True)
    return docker


@pytest.fixture
def monitor(mock_docker):
    return HealthMonitor(mock_docker)


class TestHealthMonitor:
    @pytest.mark.asyncio
    async def test_on_plugin_installed_starts_probe(self, monitor):
        """Installing a plugin starts a health probe."""
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.installed",
            plugin_name="postgres",
            data={"container_id": "abc123", "health_interval": 60},
        )
        await monitor.on_plugin_installed(event)
        assert "sb1" in monitor._tasks
        assert "postgres" in monitor._tasks["sb1"]
        # Clean up
        await monitor.stop_all()

    @pytest.mark.asyncio
    async def test_on_plugin_removed_stops_probe(self, monitor):
        """Removing a plugin stops its health probe."""
        # Install first
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.installed",
            plugin_name="redis",
            data={"container_id": "def456", "health_interval": 60},
        )
        await monitor.on_plugin_installed(event)

        # Remove
        remove_event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.removed",
            plugin_name="redis",
        )
        await monitor.on_plugin_removed(remove_event)
        assert "redis" not in monitor._tasks.get("sb1", {})

    @pytest.mark.asyncio
    async def test_ignores_wrong_event_type(self, monitor):
        """Non-install events are ignored."""
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="sandbox.created",
            plugin_name="redis",
        )
        await monitor.on_plugin_installed(event)
        assert "sb1" not in monitor._tasks

    @pytest.mark.asyncio
    async def test_stop_all_cancels_tasks(self, monitor):
        """stop_all cancels all running probes."""
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.installed",
            plugin_name="pg",
            data={"container_id": "c1", "health_interval": 60},
        )
        await monitor.on_plugin_installed(event)
        await monitor.stop_all()
        assert len(monitor._tasks) == 0

    @pytest.mark.asyncio
    async def test_no_container_id_skips(self, monitor):
        """Missing container_id doesn't start a probe."""
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.installed",
            plugin_name="pg",
            data={},
        )
        await monitor.on_plugin_installed(event)
        assert "sb1" not in monitor._tasks
