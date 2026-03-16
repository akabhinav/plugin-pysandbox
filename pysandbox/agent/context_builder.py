"""Builds the agent system prompt from installed plugins and available tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pysandbox.agent.tool_registry import AgentToolRegistry


class AgentContextBuilder:
    """Generates the agent system prompt section listing services and tools."""

    def __init__(self, tool_registry: "AgentToolRegistry") -> None:
        self._tools = tool_registry

    def build(
        self,
        sandbox_id: str,
        sandbox_name: str,
        dns_zone: str,
        installed_plugins: list[dict],
    ) -> str:
        """Build a context string describing available services and tools."""
        tools = self._tools.get_tools(sandbox_id)
        tool_names_by_plugin: dict[str, list[str]] = {}
        for plugin in installed_plugins:
            pname = plugin.get("plugin_name", "")
            tool_names_by_plugin[pname] = self._tools.get_tools_for_plugin(sandbox_id, pname)

        lines = [
            f"Sandbox: {sandbox_name} ({sandbox_id})",
            f"DNS zone: {dns_zone}",
            "",
            "Installed services and available tools:",
        ]

        for plugin in installed_plugins:
            pname = plugin.get("plugin_name", "")
            pid = plugin.get("plugin_id", "")
            ptools = tool_names_by_plugin.get(pname, [])
            lines.append(f"  {pid} ({pname}.{dns_zone}): {', '.join(ptools)}")

        lines.append("")
        lines.append(f"Total tools available: {len(tools)}")
        return "\n".join(lines)
