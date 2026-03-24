"""The plugin contract — every plugin implements this interface.

The engine only interacts with plugins through these methods.
Plugins never import from engine, runtime, agent, or other plugins.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from pysandbox.plugin.manifest import PluginManifest


@dataclass
class AgentTool:
    """A tool the agent gains when this plugin installs."""

    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable  # Async callable


@dataclass
class PluginConnection:
    """Returned after a successful install — everything needed to reach the plugin."""

    plugin_id: str
    dns_name: str
    internal_port: int
    host_port: int | None
    env_vars: dict[str, str]
    credentials: dict[str, str]
    connection_strings: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginDefinition(ABC):
    """Base class for all plugins. Implement this + decorate with @register_plugin.

    Rules:
    - Never import from engine, runtime, agent, or other plugins.
    - Never hardcode credentials — use the `credentials` dict passed in.
    - Never hardcode IPs — use DNS names via `dns_zone`.
    """

    manifest: PluginManifest

    # --- Required methods ---

    @abstractmethod
    def get_docker_config(
        self,
        plugin_name: str,
        sandbox_id: str,
        dns_zone: str,
        credentials: dict[str, str],
        config: dict[str, Any],
        version: str,
    ) -> dict:
        """Return Docker container config dict (docker-py compatible)."""

    @abstractmethod
    def get_env_vars(
        self,
        plugin_name: str,
        dns_zone: str,
        credentials: dict[str, str],
        config: dict[str, Any],
    ) -> dict[str, str]:
        """Return env vars injected into the sandbox agent and other plugins."""

    @abstractmethod
    def get_agent_tools(
        self,
        plugin_name: str,
        dns_zone: str,
        credentials: dict[str, str],
        config: dict[str, Any],
        container_id: str = "",
        docker_runtime: Any = None,
    ) -> list[AgentTool]:
        """Return tools the agent gains when this plugin installs."""

    @abstractmethod
    def generate_credentials(self, config: dict[str, Any]) -> dict[str, str]:
        """Generate fresh credentials for this plugin instance."""

    @abstractmethod
    def get_init_commands(
        self,
        plugin_name: str,
        credentials: dict[str, str],
        config: dict[str, Any],
    ) -> list[str]:
        """Shell commands run inside the container after it's healthy."""

    # --- Optional lifecycle hooks ---

    def on_install(self, connection: PluginConnection) -> None:
        """Called after successful install."""

    def on_remove(self, connection: PluginConnection) -> None:
        """Called before removal starts."""

    def on_plugin_event(
        self,
        event_type: str,
        plugin_id: str,
        connection: PluginConnection | None,
    ) -> None:
        """Called when another plugin in the same sandbox installs or removes."""

    def get_readiness_probe(self, plugin_name: str, dns_zone: str) -> dict:
        """Override to customise readiness beyond manifest health_check."""
        return {}

    def get_volume_spec(self, sandbox_id: str, plugin_name: str) -> dict:
        """Override to customise Docker volume configuration."""
        return {}
