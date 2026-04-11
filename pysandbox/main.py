"""FastAPI application factory with lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from pysandbox.agent.agent_runtime import AgentRuntime
from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.api.v1 import (
    agent, batch, branching, catalog, chaos, containers, ephemeral, export,
    fork_production, health, mcp, monitoring, plugins, pyverify, recorder, sandboxes,
    templates, terminal, time_travel, timeline, ttl, verify,
)
from pysandbox.config.settings import get_settings
from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.db.repos.sandbox_repo import SandboxRepo
from pysandbox.engine.event_bus import EventBus
from pysandbox.engine.health_monitor import HealthMonitor
from pysandbox.engine.plugin_engine import PluginEngine
from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.engine.sandbox_engine import SandboxEngine
from pysandbox.engine.activity_timeline import ActivityTimeline
from pysandbox.engine.branching import SandboxBrancher
from pysandbox.engine.chaos import ChaosEngine
from pysandbox.engine.cost_meter import CostMeter
from pysandbox.engine.ephemeral import EphemeralSandboxLauncher
from pysandbox.engine.recorder import SandboxRecorder
from pysandbox.engine.sandbox_ttl import SandboxTTLManager
from pysandbox.engine.time_travel import TimeTravelEngine
from pysandbox.engine.sandbox_seeder import SandboxSeeder
from pysandbox.engine.sandbox_verify import SandboxVerifier
from pysandbox.engine.templates import TemplateRegistry
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
    template_registry = TemplateRegistry()
    activity_timeline = ActivityTimeline()
    ttl_manager = SandboxTTLManager()
    cost_meter = CostMeter()
    chaos_engine = ChaosEngine(docker_runtime=docker_runtime, instance_repo=instance_repo)
    sandbox_recorder = SandboxRecorder()
    # Ephemeral launcher wires the existing sandbox engine + TTL manager
    # together so the `/spin` endpoint is just sugar over what we already
    # have — no parallel lifecycle to maintain.
    # It's set up after sandbox_engine is built below.
    ephemeral_launcher = None  # filled below

    # Wire event bus subscriptions
    event_bus.subscribe("plugin.installed", tool_registry.on_plugin_installed)
    event_bus.subscribe("plugin.removed", tool_registry.on_plugin_removed)
    event_bus.subscribe("plugin.installed", health_monitor.on_plugin_installed)
    event_bus.subscribe("plugin.removed", health_monitor.on_plugin_removed)
    event_bus.subscribe("*", activity_timeline.on_event)

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

    # Build verification and seeding engines
    sandbox_verifier = SandboxVerifier(
        tool_registry=tool_registry,
        instance_repo=instance_repo,
        docker_runtime=docker_runtime,
    )
    sandbox_seeder = SandboxSeeder(
        tool_registry=tool_registry,
        instance_repo=instance_repo,
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
    app.state.template_registry = template_registry
    app.state.activity_timeline = activity_timeline
    app.state.ttl_manager = ttl_manager
    app.state.sandbox_verifier = sandbox_verifier
    app.state.sandbox_seeder = sandbox_seeder
    app.state.cost_meter = cost_meter
    app.state.chaos_engine = chaos_engine
    app.state.recorder = sandbox_recorder
    app.state.ephemeral_launcher = EphemeralSandboxLauncher(
        sandbox_engine=sandbox_engine,
        ttl_manager=ttl_manager,
    )
    app.state.brancher = SandboxBrancher(
        sandbox_engine=sandbox_engine,
        instance_repo=instance_repo,
        docker_runtime=docker_runtime,
    )
    app.state.time_travel_engine = TimeTravelEngine(
        sandbox_engine=sandbox_engine,
        instance_repo=instance_repo,
        docker_runtime=docker_runtime,
    )

    # Wire TTL manager to sandbox engine and start background checker
    ttl_manager.set_engine(sandbox_engine)
    await ttl_manager.start()

    # Auto-prune orphaned networks on startup to prevent pool exhaustion
    # Protect networks belonging to active (non-destroyed) sandboxes
    try:
        all_sandboxes = await sandbox_repo.list_all()
        active_nets = {
            s["docker_network"] for s in all_sandboxes
            if s.get("status") not in ("destroyed", None)
        }
        pruned = await docker_runtime.prune_managed_networks(active_network_names=active_nets)
        if pruned:
            logger.info("startup_network_prune", count=len(pruned), networks=pruned)
    except Exception:
        logger.warning("startup_network_prune_failed")

    logger.info("pysandbox_ready")
    yield

    # Shutdown
    logger.info("pysandbox_shutting_down")
    await ttl_manager.stop()
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
    app.include_router(templates.router)
    app.include_router(monitoring.router)
    app.include_router(timeline.router)
    app.include_router(ttl.router)
    app.include_router(export.router)
    app.include_router(batch.router)
    app.include_router(terminal.router)
    app.include_router(verify.router)
    app.include_router(verify.quickstart_router)
    app.include_router(chaos.router)
    app.include_router(pyverify.router)
    app.include_router(recorder.router)
    app.include_router(ephemeral.router)
    app.include_router(branching.router)
    app.include_router(time_travel.router)
    app.include_router(fork_production.router)
    app.include_router(mcp.router)

    return app


# Module-level app for uvicorn
app = create_app()
