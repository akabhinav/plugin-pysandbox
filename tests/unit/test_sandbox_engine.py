"""Tests for sandbox engine lifecycle with mocked Docker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.agent.agent_runtime import AgentRuntime
from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.db.repos.sandbox_repo import SandboxRepo
from pysandbox.engine.event_bus import EventBus
from pysandbox.engine.plugin_engine import PluginEngine
from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.engine.sandbox_engine import SandboxEngine, SandboxState
from pysandbox.plugin.loader import discover_and_load_all
from pysandbox.runtime.dns_server import SandboxDNSManager
from pysandbox.runtime.env_injector import EnvInjector
from pysandbox.runtime.port_allocator import PortAllocator
from pysandbox.runtime.secret_manager import SecretManager


@pytest.fixture(autouse=True, scope="module")
def _load():
    discover_and_load_all()


@pytest.fixture
def mock_docker():
    docker = MagicMock()
    docker.create_network = AsyncMock(return_value="net-id")
    docker.remove_network = AsyncMock()
    docker.create_and_start = AsyncMock(return_value="container-123")
    docker.is_healthy = AsyncMock(return_value=True)
    docker.get_container_status = AsyncMock(return_value="healthy")
    docker.get_container_ip = AsyncMock(return_value="172.20.0.3")
    docker.exec_in_container = AsyncMock(return_value="ok")
    docker.stop = AsyncMock()
    docker.remove = AsyncMock()
    return docker


@pytest.fixture
def sandbox_engine(mock_docker):
    key = SecretManager.generate_key()
    event_bus = EventBus()
    instance_repo = PluginInstanceRepo()
    tool_registry = AgentToolRegistry()

    plugin_engine = PluginEngine(
        docker_runtime=mock_docker,
        dns_manager=SandboxDNSManager(),
        secret_manager=SecretManager(key),
        env_injector=EnvInjector(),
        port_allocator=PortAllocator(30000, 30100, 6300, 6400),
        event_bus=event_bus,
        resource_guard=ResourceGuard(),
        tool_registry=tool_registry,
        instance_repo=instance_repo,
    )

    agent_runtime = AgentRuntime(mock_docker, "pysandbox/pyoz:latest")

    return SandboxEngine(
        docker_runtime=mock_docker,
        dns_manager=plugin_engine._dns,
        port_allocator=plugin_engine._ports,
        plugin_engine=plugin_engine,
        resource_guard=plugin_engine._resources,
        event_bus=event_bus,
        agent_runtime=agent_runtime,
        sandbox_repo=SandboxRepo(),
    )


class TestSandboxCreate:
    @pytest.mark.asyncio
    async def test_create_empty_sandbox(self, sandbox_engine, mock_docker):
        """Create a sandbox with no plugins."""
        sandbox = await sandbox_engine.create(name="test-sandbox")

        assert sandbox["name"] == "test-sandbox"
        assert sandbox["status"] == SandboxState.RUNNING.value
        assert sandbox["docker_network"].startswith("pysb-")
        assert sandbox["dns_zone"].endswith(".sandbox.local")
        mock_docker.create_network.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_plugins(self, sandbox_engine, mock_docker):
        """Create a sandbox with initial plugins."""
        sandbox = await sandbox_engine.create(
            name="full-sandbox",
            plugins=[
                {"plugin_id": "redis", "name": "my-redis"},
            ],
        )

        assert sandbox["status"] == SandboxState.RUNNING.value
        # Docker should have been called for network + agent + redis containers
        assert mock_docker.create_and_start.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_assigns_unique_ids(self, sandbox_engine, mock_docker):
        """Each sandbox gets a unique ID."""
        sb1 = await sandbox_engine.create(name="sb1")
        sb2 = await sandbox_engine.create(name="sb2")
        assert sb1["id"] != sb2["id"]

    @pytest.mark.asyncio
    async def test_create_stores_sandbox(self, sandbox_engine, mock_docker):
        """Created sandbox is retrievable."""
        sb = await sandbox_engine.create(name="stored")
        result = await sandbox_engine.get(sb["id"])
        assert result is not None
        assert result["name"] == "stored"


class TestSandboxPauseResume:
    @pytest.mark.asyncio
    async def test_pause_sandbox(self, sandbox_engine, mock_docker):
        """Pausing stops containers."""
        sb = await sandbox_engine.create(name="pausable")
        await sandbox_engine.pause(sb["id"])

        result = await sandbox_engine.get(sb["id"])
        assert result["status"] == SandboxState.PAUSED.value

    @pytest.mark.asyncio
    async def test_resume_sandbox(self, sandbox_engine, mock_docker):
        """Resuming restarts containers."""
        sb = await sandbox_engine.create(name="resumable")
        await sandbox_engine.pause(sb["id"])
        await sandbox_engine.resume(sb["id"])

        result = await sandbox_engine.get(sb["id"])
        assert result["status"] == SandboxState.RUNNING.value


class TestSandboxDestroy:
    @pytest.mark.asyncio
    async def test_destroy_sandbox(self, sandbox_engine, mock_docker):
        """Destroying cleans up everything."""
        sb = await sandbox_engine.create(name="destroyable")
        await sandbox_engine.destroy(sb["id"])

        result = await sandbox_engine.get(sb["id"])
        assert result["status"] == SandboxState.DESTROYED.value
        mock_docker.remove_network.assert_called()

    @pytest.mark.asyncio
    async def test_destroy_with_plugins(self, sandbox_engine, mock_docker):
        """Destroying removes all installed plugins first."""
        sb = await sandbox_engine.create(
            name="full",
            plugins=[{"plugin_id": "redis", "name": "r"}],
        )
        await sandbox_engine.destroy(sb["id"])

        result = await sandbox_engine.get(sb["id"])
        assert result["status"] == SandboxState.DESTROYED.value


class TestSandboxList:
    @pytest.mark.asyncio
    async def test_list_sandboxes(self, sandbox_engine, mock_docker):
        """List returns all sandboxes."""
        await sandbox_engine.create(name="s1")
        await sandbox_engine.create(name="s2")

        all_sandboxes = await sandbox_engine.list_all()
        names = {s["name"] for s in all_sandboxes}
        assert "s1" in names
        assert "s2" in names


class TestSandboxEvents:
    @pytest.mark.asyncio
    async def test_create_emits_event(self, sandbox_engine, mock_docker):
        events = []

        async def handler(event):
            events.append(event)

        sandbox_engine._events.subscribe("sandbox.created", handler)
        await sandbox_engine.create(name="evented")
        assert len(events) == 1
        assert events[0].event_type == "sandbox.created"

    @pytest.mark.asyncio
    async def test_destroy_emits_event(self, sandbox_engine, mock_docker):
        events = []

        async def handler(event):
            events.append(event)

        sandbox_engine._events.subscribe("sandbox.destroyed", handler)
        sb = await sandbox_engine.create(name="evented2")
        await sandbox_engine.destroy(sb["id"])
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_pause_emits_event(self, sandbox_engine, mock_docker):
        events = []

        async def handler(event):
            events.append(event)

        sandbox_engine._events.subscribe("sandbox.paused", handler)
        sb = await sandbox_engine.create(name="evented3")
        await sandbox_engine.pause(sb["id"])
        assert len(events) == 1


class TestTopologicalSort:
    def test_sort_by_startup_order(self):
        plugins = [
            {"plugin_id": "kafka", "startup_order": 30},
            {"plugin_id": "postgres", "startup_order": 10},
            {"plugin_id": "redis", "startup_order": 20},
        ]
        sorted_plugins = SandboxEngine._topological_sort(plugins)
        assert [p["plugin_id"] for p in sorted_plugins] == ["postgres", "redis", "kafka"]

    def test_default_order(self):
        plugins = [
            {"plugin_id": "a"},
            {"plugin_id": "b"},
        ]
        # Both default to 50
        sorted_plugins = SandboxEngine._topological_sort(plugins)
        assert len(sorted_plugins) == 2
