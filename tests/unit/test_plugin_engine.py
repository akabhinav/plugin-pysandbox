"""Tests for plugin engine install/remove with mocked Docker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.engine.event_bus import EventBus
from pysandbox.engine.plugin_engine import PluginEngine
from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.plugin.exceptions import ConfigValidationError, PluginInstallError
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
    docker.create_and_start = AsyncMock(return_value="container-123")
    docker.is_healthy = AsyncMock(return_value=True)
    docker.get_container_status = AsyncMock(return_value="healthy")
    docker.get_container_ip = AsyncMock(return_value="172.20.0.3")
    docker.exec_in_container = AsyncMock(return_value="ok")
    docker.stop = AsyncMock()
    docker.remove = AsyncMock()
    return docker


@pytest.fixture
def engine(mock_docker):
    key = SecretManager.generate_key()
    return PluginEngine(
        docker_runtime=mock_docker,
        dns_manager=SandboxDNSManager(),
        secret_manager=SecretManager(key),
        env_injector=EnvInjector(),
        port_allocator=PortAllocator(30000, 30100, 6300, 6400),
        event_bus=EventBus(),
        resource_guard=ResourceGuard(),
        tool_registry=AgentToolRegistry(),
        instance_repo=PluginInstanceRepo(),
    )


class TestPluginInstall:
    @pytest.mark.asyncio
    async def test_install_postgres(self, engine, mock_docker):
        """Full postgres install through the engine."""
        # Start DNS for sandbox
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)

        conn = await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="postgres",
            plugin_name="my-postgres",
        )

        assert conn.plugin_id == "postgres"
        assert conn.dns_name == "my-postgres.abc.sandbox.local"
        assert conn.internal_port == 5432
        assert "POSTGRES_URL" in conn.env_vars
        mock_docker.create_and_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_redis(self, engine, mock_docker):
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)

        conn = await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="my-redis",
        )

        assert conn.plugin_id == "redis"
        assert "REDIS_URL" in conn.env_vars

    @pytest.mark.asyncio
    async def test_install_registers_tools(self, engine, mock_docker):
        """Tools are registered after install."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="postgres",
            plugin_name="pg",
        )

        tools = engine._tools.get_tools("sb1")
        assert len(tools) > 0
        tool_names = {t.name for t in tools}
        assert "sql_query" in tool_names

    @pytest.mark.asyncio
    async def test_install_registers_dns(self, engine, mock_docker):
        """DNS is registered after install."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="my-redis",
        )

        ip = await engine._dns.resolve("sb1", "my-redis.abc.sandbox.local")
        assert ip == "172.20.0.3"

    @pytest.mark.asyncio
    async def test_install_injects_env(self, engine, mock_docker):
        """Env vars are injected after install."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="my-redis",
        )

        env = engine._env.get_all("sb1")
        assert "REDIS_URL" in env
        assert "REDIS_HOST" in env

    @pytest.mark.asyncio
    async def test_install_persists_instance(self, engine, mock_docker):
        """Instance is persisted to repo."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="my-redis",
        )

        inst = await engine._repo.get_instance("sb1", "my-redis")
        assert inst is not None
        assert inst["plugin_id"] == "redis"
        assert inst["container_id"] == "container-123"
        assert inst["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_install_runs_init_commands(self, engine, mock_docker):
        """Init commands are run after container is healthy."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="postgres",
            plugin_name="pg",
            config={},
        )

        # Postgres runs init commands for uuid-ossp and pgcrypto
        assert mock_docker.exec_in_container.call_count >= 2

    @pytest.mark.asyncio
    async def test_install_with_expose(self, engine, mock_docker):
        """Exposed plugins get a host port."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        conn = await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="r",
            expose=True,
        )

        assert conn.host_port is not None
        assert 30000 <= conn.host_port <= 30100

    @pytest.mark.asyncio
    async def test_install_with_version(self, engine, mock_docker):
        """Custom version is passed to docker config."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="postgres",
            plugin_name="pg",
            version="15",
        )

        call_args = mock_docker.create_and_start.call_args
        docker_cfg = call_args.kwargs["docker_config"]
        assert docker_cfg["image"] == "postgres:15"

    @pytest.mark.asyncio
    async def test_install_emits_event(self, engine, mock_docker):
        """Install emits a plugin.installed event."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        engine._events.subscribe("plugin.installed", handler)
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="r",
        )

        assert len(events_received) == 1
        assert events_received[0].plugin_id == "redis"


class TestPluginInstallRollback:
    @pytest.mark.asyncio
    async def test_rollback_on_health_timeout(self, engine, mock_docker):
        """Failed health check triggers rollback."""
        mock_docker.is_healthy = AsyncMock(return_value=False)
        mock_docker.get_container_status = AsyncMock(return_value="starting")
        mock_docker.get_logs = AsyncMock(return_value="waiting for startup...")
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)

        with pytest.raises(PluginInstallError):
            await engine.install(
                sandbox_id="sb1",
                docker_network="pysb-abc",
                dns_zone="abc.sandbox.local",
                plugin_id="redis",
                plugin_name="r",
            )

        # Container should have been removed in rollback
        mock_docker.remove.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_on_container_start_failure(self, engine, mock_docker):
        """Failed container start triggers rollback."""
        mock_docker.create_and_start = AsyncMock(side_effect=RuntimeError("docker error"))
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)

        with pytest.raises(PluginInstallError):
            await engine.install(
                sandbox_id="sb1",
                docker_network="pysb-abc",
                dns_zone="abc.sandbox.local",
                plugin_id="redis",
                plugin_name="r",
            )


class TestPluginRemove:
    @pytest.mark.asyncio
    async def test_remove_plugin(self, engine, mock_docker):
        """Remove cleans up all resources."""
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="my-redis",
        )

        await engine.remove("sb1", "my-redis")

        # Tools unregistered
        assert len(engine._tools.get_tools("sb1")) == 0
        # DNS deregistered
        ip = await engine._dns.resolve("sb1", "my-redis.abc.sandbox.local")
        assert ip is None
        # Container stopped and removed
        mock_docker.stop.assert_called()
        mock_docker.remove.assert_called()
        # Instance marked removed
        inst = await engine._repo.get_instance("sb1", "my-redis")
        assert inst is None  # Filtered out by list

    @pytest.mark.asyncio
    async def test_remove_emits_event(self, engine, mock_docker):
        """Remove emits a plugin.removed event."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        engine._events.subscribe("plugin.removed", handler)
        await engine._dns.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await engine.install(
            sandbox_id="sb1",
            docker_network="pysb-abc",
            dns_zone="abc.sandbox.local",
            plugin_id="redis",
            plugin_name="r",
        )

        await engine.remove("sb1", "r")

        assert len(events_received) == 1
        assert events_received[0].event_type == "plugin.removed"

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_noop(self, engine, mock_docker):
        """Removing a non-existent plugin doesn't error."""
        await engine.remove("sb1", "not-here")  # Should not raise


class TestConnectionStrings:
    def test_build_connection_strings(self):
        env = {
            "POSTGRES_URL": "postgresql://...",
            "REDIS_URI": "redis://...",
            "POSTGRES_HOST": "pg.local",
            "PORT": "5432",
        }
        result = PluginEngine._build_connection_strings(env)
        assert "POSTGRES_URL" in result
        assert "REDIS_URI" in result
        assert "POSTGRES_HOST" not in result
        assert "PORT" not in result
