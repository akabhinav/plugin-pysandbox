"""FastAPI application factory with lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from pysandbox.agent.agent_runtime import AgentRuntime
from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.api.v1 import agent, catalog, containers, health, plugins, sandboxes
from pysandbox.config.settings import get_settings
from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.db.repos.sandbox_repo import SandboxRepo
from pysandbox.engine.event_bus import EventBus
from pysandbox.engine.health_monitor import HealthMonitor
from pysandbox.engine.plugin_engine import PluginEngine
from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.engine.sandbox_engine import SandboxEngine
from pysandbox.plugin.loader import discover_and_load_all
from pysandbox.runtime.dns_server import SandboxDNSManager
from pysandbox.runtime.docker_runtime import DockerRuntime
from pysandbox.runtime.env_injector import EnvInjector
from pysandbox.runtime.port_allocator import PortAllocator
from pysandbox.runtime.secret_manager import SecretManager

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all components on startup, clean up on shutdown."""
    settings = get_settings()
    logger.info("pysandbox_starting", env=settings.PYSANDBOX_ENV)

    # Discover and register all plugins
    discover_and_load_all()

    # Initialize components (dependency injection via constructor)
    docker_runtime = DockerRuntime(settings.DOCKER_SOCKET)
    dns_manager = SandboxDNSManager()
    secret_manager = SecretManager(
        settings.SECRET_ENCRYPTION_KEY.get_secret_value() or SecretManager.generate_key()
    )
    env_injector = EnvInjector()
    port_allocator = PortAllocator(
        host_range_start=settings.HOST_PORT_RANGE_START,
        host_range_end=settings.HOST_PORT_RANGE_END,
        dns_range_start=settings.DNS_PORT_RANGE_START,
        dns_range_end=settings.DNS_PORT_RANGE_END,
    )
    event_bus = EventBus()
    resource_guard = ResourceGuard()
    tool_registry = AgentToolRegistry()
    agent_runtime = AgentRuntime(docker_runtime, settings.AGENT_IMAGE)
    sandbox_repo = SandboxRepo()
    instance_repo = PluginInstanceRepo()
    health_monitor = HealthMonitor(docker_runtime)

    # Wire event bus subscriptions
    event_bus.subscribe("plugin.installed", tool_registry.on_plugin_installed)
    event_bus.subscribe("plugin.removed", tool_registry.on_plugin_removed)
    event_bus.subscribe("plugin.installed", health_monitor.on_plugin_installed)
    event_bus.subscribe("plugin.removed", health_monitor.on_plugin_removed)

    # Build engines
    plugin_engine = PluginEngine(
        docker_runtime=docker_runtime,
        dns_manager=dns_manager,
        secret_manager=secret_manager,
        env_injector=env_injector,
        port_allocator=port_allocator,
        event_bus=event_bus,
        resource_guard=resource_guard,
        tool_registry=tool_registry,
        instance_repo=instance_repo,
    )
    sandbox_engine = SandboxEngine(
        docker_runtime=docker_runtime,
        dns_manager=dns_manager,
        port_allocator=port_allocator,
        plugin_engine=plugin_engine,
        resource_guard=resource_guard,
        event_bus=event_bus,
        agent_runtime=agent_runtime,
        sandbox_repo=sandbox_repo,
    )

    # Store on app state for endpoint access
    app.state.sandbox_engine = sandbox_engine
    app.state.plugin_engine = plugin_engine
    app.state.event_bus = event_bus
    app.state.tool_registry = tool_registry
    app.state.agent_runtime = agent_runtime
    app.state.docker_runtime = docker_runtime
    app.state.dns_manager = dns_manager
    app.state.env_injector = env_injector
    app.state.secret_manager = secret_manager
    app.state.plugin_instance_repo = instance_repo

    logger.info("pysandbox_ready")
    yield

    # Shutdown
    logger.info("pysandbox_shutting_down")
    await health_monitor.stop_all()
    await docker_runtime.close()
    logger.info("pysandbox_stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="PySandbox",
        description="Plugin-based enterprise sandbox runtime",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register API routes
    app.include_router(health.router)
    app.include_router(catalog.router)
    app.include_router(sandboxes.router)
    app.include_router(plugins.router)
    app.include_router(agent.router)
    app.include_router(containers.router)

    return app


# Module-level app for uvicorn
app = create_app()
