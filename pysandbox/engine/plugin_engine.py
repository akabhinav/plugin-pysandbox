"""Plugin install/remove orchestrator — completely agnostic to specific plugins.

Calls only methods on PluginDefinition. Every step is rollback-safe.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from pysandbox.plugin.base import PluginConnection
from pysandbox.plugin.exceptions import ConfigValidationError, PluginInstallError, PluginRemoveError
from pysandbox.plugin.registry import get_plugin

if TYPE_CHECKING:
    from pysandbox.agent.tool_registry import AgentToolRegistry
    from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
    from pysandbox.engine.event_bus import EventBus, SandboxEvent
    from pysandbox.engine.resource_guard import ResourceGuard
    from pysandbox.runtime.dns_server import SandboxDNSManager
    from pysandbox.runtime.docker_runtime import DockerRuntime
    from pysandbox.runtime.env_injector import EnvInjector
    from pysandbox.runtime.port_allocator import PortAllocator
    from pysandbox.runtime.secret_manager import SecretManager

logger = structlog.get_logger()


class PluginInstallStep(str, Enum):
    VALIDATE = "validate"
    ALLOCATE_RESOURCES = "allocate_resources"
    GENERATE_CREDENTIALS = "generate_credentials"
    CREATE_CONTAINER = "create_container"
    WAIT_HEALTHY = "wait_healthy"
    REGISTER_DNS = "register_dns"
    INJECT_ENV = "inject_env"
    RUN_INIT = "run_init"
    REGISTER_TOOLS = "register_tools"
    EMIT_EVENT = "emit_event"


class PluginRemoveStep(str, Enum):
    CALL_ON_REMOVE = "call_on_remove"
    UNREGISTER_TOOLS = "unregister_tools"
    REMOVE_ENV = "remove_env"
    DEREGISTER_DNS = "deregister_dns"
    STOP_CONTAINER = "stop_container"
    REMOVE_CONTAINER = "remove_container"
    REMOVE_VOLUME = "remove_volume"
    DELETE_CREDENTIALS = "delete_credentials"
    RELEASE_RESOURCES = "release_resources"
    EMIT_EVENT = "emit_event"


class PluginEngine:
    """Orchestrates plugin install and removal through the PluginDefinition contract."""

    def __init__(
        self,
        docker_runtime: "DockerRuntime",
        dns_manager: "SandboxDNSManager",
        secret_manager: "SecretManager",
        env_injector: "EnvInjector",
        port_allocator: "PortAllocator",
        event_bus: "EventBus",
        resource_guard: "ResourceGuard",
        tool_registry: "AgentToolRegistry",
        instance_repo: "PluginInstanceRepo",
    ) -> None:
        self._docker = docker_runtime
        self._dns = dns_manager
        self._secrets = secret_manager
        self._env = env_injector
        self._ports = port_allocator
        self._events = event_bus
        self._resources = resource_guard
        self._tools = tool_registry
        self._repo = instance_repo

    async def install(
        self,
        sandbox_id: str,
        docker_network: str,
        dns_zone: str,
        plugin_id: str,
        plugin_name: str,
        version: str | None = None,
        config: dict[str, Any] | None = None,
        expose: bool = False,
    ) -> PluginConnection:
        """Install a plugin. Each step is tracked; failures trigger rollback."""
        config = config or {}
        definition = get_plugin(plugin_id)
        version = version or definition.manifest.default_version
        rollback_stack: list[tuple[str, Any]] = []  # (description, async_callable)

        log = logger.bind(sandbox_id=sandbox_id, plugin_id=plugin_id, plugin_name=plugin_name)
        log.info("plugin_install_start")

        try:
            # Step 1: Validate config against manifest schema
            self._validate_config(definition, config)

            # Step 2: Check resource quota
            self._resources.check_and_reserve(sandbox_id, definition.manifest)
            rollback_stack.append(("release_resources", lambda: self._resources.release(sandbox_id, definition.manifest)))

            # Step 3: Generate credentials
            credentials = definition.generate_credentials(config)
            encrypted = self._secrets.encrypt(credentials)
            rollback_stack.append(("delete_credentials", lambda: None))

            # Step 4: Allocate ports
            internal_port = definition.manifest.ports[0].port if definition.manifest.ports else 0
            host_port = self._ports.allocate_host_port() if expose else None
            if host_port:
                rollback_stack.append(("release_port", lambda hp=host_port: self._ports.release_host_port(hp)))

            # Step 5: Get docker config and start container
            docker_cfg = definition.get_docker_config(
                plugin_name, sandbox_id, dns_zone, credentials, config, version,
            )
            container_id = await self._docker.create_and_start(
                container_name=f"pysb-{sandbox_id[:8]}-{plugin_name}",
                network=docker_network,
                network_alias=plugin_name,
                host_port=host_port,
                container_port=internal_port,
                docker_config=docker_cfg,
                cpu_limit=float(definition.manifest.resources.cpu),
                memory_limit=definition.manifest.resources.memory,
            )
            rollback_stack.append(("remove_container", lambda cid=container_id: self._docker.remove(cid, force=True)))

            # Step 6: Wait for healthy
            timeout = definition.manifest.health_check.timeout_seconds * definition.manifest.health_check.retries
            await self._wait_healthy(container_id, timeout)

            # Step 7: Get container IP and register DNS
            container_ip = await self._docker.get_container_ip(container_id, docker_network)
            await self._dns.register(sandbox_id, plugin_name, container_ip)
            rollback_stack.append(("deregister_dns", lambda: self._dns.deregister(sandbox_id, plugin_name)))

            # Step 8: Inject env vars
            env_vars = definition.get_env_vars(plugin_name, dns_zone, credentials, config)
            await self._env.inject(sandbox_id, env_vars)
            rollback_stack.append(("remove_env", lambda keys=list(env_vars): self._env.remove(sandbox_id, keys)))

            # Step 9: Run init commands
            init_cmds = definition.get_init_commands(plugin_name, credentials, config)
            for cmd in init_cmds:
                await self._docker.exec_in_container(container_id, cmd)

            # Step 10: Register agent tools
            tools = definition.get_agent_tools(plugin_name, dns_zone, credentials, config)
            tool_names = [t.name for t in tools]
            await self._tools.register_tools(sandbox_id, plugin_name, tools)
            rollback_stack.append(("unregister_tools", lambda: self._tools.unregister_tools(sandbox_id, plugin_name)))

            # Build connection info
            connection = PluginConnection(
                plugin_id=plugin_id,
                dns_name=f"{plugin_name}.{dns_zone}",
                internal_port=internal_port,
                host_port=host_port,
                env_vars=env_vars,
                credentials=credentials,
                connection_strings=self._build_connection_strings(env_vars),
            )

            # Step 11: Lifecycle hook + events
            definition.on_install(connection)
            await self._events.emit(
                _make_event(sandbox_id, "plugin.installed", plugin_id, plugin_name, {
                    "connection": connection,
                    "container_id": container_id,
                    "tools": tools,
                    "tool_names": tool_names,
                    "health_interval": definition.manifest.health_check.interval_seconds,
                })
            )

            # Persist instance
            await self._repo.create_instance(
                sandbox_id=sandbox_id,
                plugin_id=plugin_id,
                plugin_name=plugin_name,
                version=version,
                config=config,
                credentials_encrypted=encrypted,
                container_id=container_id,
                container_ip=container_ip,
                internal_port=internal_port,
                host_port=host_port,
                env_var_keys=list(env_vars),
                agent_tool_names=tool_names,
                startup_order=definition.manifest.startup_order,
            )

            log.info("plugin_install_complete", tools=len(tools))
            return connection

        except Exception as e:
            log.error("plugin_install_failed", error=str(e))
            await self._rollback(rollback_stack)
            raise PluginInstallError(plugin_id, str(e)) from e

    async def remove(
        self,
        sandbox_id: str,
        plugin_name: str,
    ) -> None:
        """Remove a plugin. Best-effort cleanup of all resources."""
        instance = await self._repo.get_instance(sandbox_id, plugin_name)
        if not instance:
            return

        log = logger.bind(sandbox_id=sandbox_id, plugin_name=plugin_name)
        log.info("plugin_remove_start")

        definition = get_plugin(instance["plugin_id"])

        # Call on_remove hook
        try:
            connection = self._build_connection_from_instance(instance)
            definition.on_remove(connection)
        except Exception:
            log.exception("on_remove_hook_error")

        # Unregister tools
        await self._tools.unregister_tools(sandbox_id, plugin_name)

        # Remove env vars
        await self._env.remove(sandbox_id, instance.get("env_var_keys", []))

        # Deregister DNS
        await self._dns.deregister(sandbox_id, plugin_name)

        # Stop and remove container
        container_id = instance.get("container_id")
        if container_id:
            await self._docker.stop(container_id)
            await self._docker.remove(container_id, force=True)

        # Release resources
        self._resources.release(sandbox_id, definition.manifest)

        # Emit event
        await self._events.emit(
            _make_event(sandbox_id, "plugin.removed", instance["plugin_id"], plugin_name, {
                "tool_names": instance.get("agent_tool_names", []),
            })
        )

        # Mark removed in DB
        await self._repo.mark_removed(sandbox_id, plugin_name)
        log.info("plugin_remove_complete")

    def _validate_config(self, definition, config: dict) -> None:
        """Validate user config against manifest's config_params."""
        for param in definition.manifest.config_params:
            if param.required and param.key not in config:
                raise ConfigValidationError(f"Missing required config: {param.key}")

    async def _wait_healthy(self, container_id: str, timeout: int) -> None:
        """Poll container health until healthy or timeout."""
        elapsed = 0
        interval = 2
        while elapsed < timeout:
            if await self._docker.is_healthy(container_id):
                return
            await asyncio.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"Container {container_id[:12]} not healthy after {timeout}s")

    async def _rollback(self, stack: list[tuple[str, Any]]) -> None:
        """Execute rollback steps in reverse order. Each step is best-effort."""
        for desc, fn in reversed(stack):
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=10)
            except Exception as e:
                logger.warning("rollback_step_failed", step=desc, error=str(e))

    @staticmethod
    def _build_connection_strings(env_vars: dict[str, str]) -> dict[str, str]:
        """Extract connection strings from env vars (keys ending in _URL or _URI)."""
        return {
            k: v for k, v in env_vars.items()
            if k.endswith("_URL") or k.endswith("_URI")
        }

    @staticmethod
    def _build_connection_from_instance(instance: dict) -> PluginConnection:
        return PluginConnection(
            plugin_id=instance["plugin_id"],
            dns_name=instance.get("dns_name", ""),
            internal_port=instance.get("internal_port", 0),
            host_port=instance.get("host_port"),
            env_vars=instance.get("env_vars", {}),
            credentials={},  # Not decrypted here for safety
            connection_strings={},
        )


def _make_event(
    sandbox_id: str, event_type: str, plugin_id: str, plugin_name: str, data: dict
) -> "SandboxEvent":
    from pysandbox.engine.event_bus import SandboxEvent
    return SandboxEvent(
        sandbox_id=sandbox_id,
        event_type=event_type,
        plugin_id=plugin_id,
        plugin_name=plugin_name,
        data=data,
    )
