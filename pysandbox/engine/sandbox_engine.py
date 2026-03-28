"""Sandbox lifecycle orchestrator — create, pause, resume, destroy."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from pysandbox.config.settings import get_settings
from pysandbox.engine.event_bus import SandboxEvent

if TYPE_CHECKING:
    from pysandbox.agent.agent_runtime import AgentRuntime
    from pysandbox.db.repos.sandbox_repo import SandboxRepo
    from pysandbox.engine.event_bus import EventBus
    from pysandbox.engine.plugin_engine import PluginEngine
    from pysandbox.engine.resource_guard import ResourceGuard
    from pysandbox.runtime.dns_server import SandboxDNSManager
    from pysandbox.runtime.docker_runtime import DockerRuntime
    from pysandbox.runtime.port_allocator import PortAllocator

logger = structlog.get_logger()


class SandboxState(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    RESUMING = "resuming"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    ERROR = "error"


class SandboxEngine:
    """Manages sandbox lifecycle — delegates plugin work to PluginEngine."""

    def __init__(
        self,
        docker_runtime: "DockerRuntime",
        dns_manager: "SandboxDNSManager",
        port_allocator: "PortAllocator",
        plugin_engine: "PluginEngine",
        resource_guard: "ResourceGuard",
        event_bus: "EventBus",
        agent_runtime: "AgentRuntime",
        sandbox_repo: "SandboxRepo",
    ) -> None:
        self._docker = docker_runtime
        self._dns = dns_manager
        self._ports = port_allocator
        self._plugins = plugin_engine
        self._resources = resource_guard
        self._events = event_bus
        self._agent = agent_runtime
        self._repo = sandbox_repo

    async def create(
        self,
        name: str,
        owner_id: str = "default",
        org_id: str | None = None,
        plugins: list[dict[str, Any]] | None = None,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new sandbox with isolated network, DNS, and optional plugins."""
        settings = get_settings()
        sandbox_id = str(uuid4())
        short_id = sandbox_id[:8]
        log = logger.bind(sandbox_id=sandbox_id, name=name)
        log.info("sandbox_create_start")

        sandbox = {
            "id": sandbox_id,
            "name": name,
            "owner_id": owner_id,
            "org_id": org_id,
            "status": SandboxState.CREATING.value,
            "docker_network": f"{settings.DOCKER_NETWORK_PREFIX}-{short_id}",
            "dns_zone": f"{short_id}.{settings.SANDBOX_DNS_DOMAIN}",
            "dns_port": self._ports.allocate_dns_port(),
            "total_cpu": settings.DEFAULT_SANDBOX_CPU_LIMIT,
            "total_memory_gb": settings.DEFAULT_SANDBOX_MEMORY_LIMIT_GB,
            "total_disk_gb": settings.DEFAULT_SANDBOX_DISK_LIMIT_GB,
            "tags": tags or {},
        }

        await self._repo.create(sandbox)

        try:
            # Create isolated Docker network
            await self._docker.create_network(
                name=sandbox["docker_network"],
                labels={"pysandbox.sandbox_id": sandbox_id},
            )

            # Initialize resource guard
            self._resources.init_sandbox(
                sandbox_id,
                max_cpu=sandbox["total_cpu"],
                max_memory_gb=sandbox["total_memory_gb"],
                max_disk_gb=sandbox["total_disk_gb"],
                max_plugins=settings.MAX_PLUGINS_PER_SANDBOX,
            )

            # Start per-sandbox DNS server
            await self._dns.start_for_sandbox(sandbox_id, sandbox["dns_zone"], sandbox["dns_port"])

            # Start agent runtime
            await self._agent.start(sandbox_id, sandbox["docker_network"], sandbox["dns_zone"])

            # Install requested plugins in dependency order
            if plugins:
                ordered = self._topological_sort(plugins)
                for spec in ordered:
                    await self._plugins.install(
                        sandbox_id=sandbox_id,
                        docker_network=sandbox["docker_network"],
                        dns_zone=sandbox["dns_zone"],
                        plugin_id=spec["plugin_id"],
                        plugin_name=spec.get("name", spec["plugin_id"]),
                        version=spec.get("version"),
                        config=spec.get("config", {}),
                        expose=spec.get("expose", False),
                    )

            sandbox["status"] = SandboxState.RUNNING.value
            await self._repo.update(sandbox)
            await self._events.emit(SandboxEvent(sandbox_id=sandbox_id, event_type="sandbox.created"))
            log.info("sandbox_create_complete")
            return sandbox

        except Exception as e:
            log.error("sandbox_create_failed", error=str(e))
            sandbox["status"] = SandboxState.ERROR.value
            sandbox["error"] = str(e)
            await self._repo.update(sandbox)
            # Clean up the network we created so it doesn't leak
            try:
                await self._docker.remove_network(sandbox["docker_network"])
            except Exception:
                log.warning("cleanup_network_on_error_failed")
            raise

    async def pause(self, sandbox_id: str) -> None:
        """Stop all containers but retain network, volumes, and DNS records."""
        log = logger.bind(sandbox_id=sandbox_id)
        log.info("sandbox_pause_start")

        instances = await self._plugins._repo.list_instances(sandbox_id)
        for inst in instances:
            if inst.get("container_id"):
                await self._docker.stop(inst["container_id"])

        await self._agent.stop(sandbox_id)
        await self._repo.update_status(sandbox_id, SandboxState.PAUSED.value)
        await self._events.emit(SandboxEvent(sandbox_id=sandbox_id, event_type="sandbox.paused"))
        log.info("sandbox_paused")

    async def resume(self, sandbox_id: str) -> None:
        """Restart all containers in startup order."""
        log = logger.bind(sandbox_id=sandbox_id)
        log.info("sandbox_resume_start")
        await self._repo.update_status(sandbox_id, SandboxState.RESUMING.value)

        sandbox = await self._repo.get(sandbox_id)
        instances = await self._plugins._repo.list_instances(sandbox_id)
        # Sort by startup_order
        instances.sort(key=lambda i: i.get("startup_order", 50))

        for inst in instances:
            if inst.get("container_id"):
                await self._docker.start(inst["container_id"])
                # Wait for healthy
                hc_timeout = 90
                await self._plugins._wait_healthy(inst["container_id"], hc_timeout)

        await self._agent.start(sandbox_id, sandbox["docker_network"], sandbox["dns_zone"])
        await self._repo.update_status(sandbox_id, SandboxState.RUNNING.value)
        await self._events.emit(SandboxEvent(sandbox_id=sandbox_id, event_type="sandbox.resumed"))
        log.info("sandbox_resumed")

    async def destroy(self, sandbox_id: str) -> None:
        """Remove all plugins, stop DNS, destroy network. Irreversible.

        Tolerates missing Docker resources (e.g. from a failed create).
        Always marks the sandbox as destroyed regardless of cleanup errors.
        """
        log = logger.bind(sandbox_id=sandbox_id)
        log.info("sandbox_destroy_start")
        await self._repo.update_status(sandbox_id, SandboxState.DESTROYING.value)

        # Remove plugins in reverse install order
        instances = await self._plugins._repo.list_instances(sandbox_id)
        for inst in reversed(instances):
            try:
                await self._plugins.remove(sandbox_id, inst["plugin_name"])
            except Exception:
                log.exception("plugin_remove_error", plugin=inst["plugin_name"])
                # Force remove container even if plugin remove failed
                cid = inst.get("container_id")
                if cid:
                    try:
                        await self._docker.remove(cid, force=True)
                    except Exception:
                        pass

        # Stop agent and DNS
        try:
            await self._agent.destroy(sandbox_id)
        except Exception:
            log.warning("agent_destroy_failed")
        try:
            await self._dns.stop_for_sandbox(sandbox_id)
        except Exception:
            log.warning("dns_stop_failed")

        # Remove network (force-disconnects remaining containers)
        sandbox = await self._repo.get(sandbox_id)
        if sandbox:
            try:
                await self._docker.remove_network(sandbox["docker_network"])
            except Exception:
                log.warning("network_remove_failed_on_destroy")

        self._resources.remove_sandbox(sandbox_id)
        await self._repo.update_status(sandbox_id, SandboxState.DESTROYED.value)
        await self._events.emit(SandboxEvent(sandbox_id=sandbox_id, event_type="sandbox.destroyed"))
        log.info("sandbox_destroyed")

    async def get(self, sandbox_id: str) -> dict[str, Any] | None:
        return await self._repo.get(sandbox_id)

    async def list_all(self) -> list[dict[str, Any]]:
        return await self._repo.list_all()

    @staticmethod
    def _topological_sort(plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort plugins by startup_order (simple numeric sort for now)."""
        return sorted(plugins, key=lambda p: p.get("startup_order", 50))
