"""Per-sandbox agent tool registry — tools auto-appear/disappear with plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pysandbox.engine.event_bus import SandboxEvent
    from pysandbox.plugin.base import AgentTool

logger = structlog.get_logger()


class AgentToolRegistry:
    """Dynamic tool registry. Tools are added when plugins install, removed when they uninstall."""

    def __init__(self) -> None:
        # sandbox_id → {tool_name → AgentTool}
        self._tools: dict[str, dict[str, "AgentTool"]] = {}
        # sandbox_id → {plugin_name → [tool_names]}
        self._plugin_tools: dict[str, dict[str, list[str]]] = {}

    async def register_tools(
        self, sandbox_id: str, plugin_name: str, tools: list["AgentTool"]
    ) -> None:
        """Register tools for a plugin in a sandbox."""
        self._tools.setdefault(sandbox_id, {})
        self._plugin_tools.setdefault(sandbox_id, {})

        tool_names = []
        for tool in tools:
            self._tools[sandbox_id][tool.name] = tool
            tool_names.append(tool.name)

        self._plugin_tools[sandbox_id][plugin_name] = tool_names
        logger.info(
            "tools_registered",
            sandbox_id=sandbox_id,
            plugin=plugin_name,
            tools=tool_names,
            total=len(self._tools[sandbox_id]),
        )

    async def unregister_tools(self, sandbox_id: str, plugin_name: str) -> None:
        """Remove all tools belonging to a plugin."""
        tool_names = self._plugin_tools.get(sandbox_id, {}).pop(plugin_name, [])
        sandbox_tools = self._tools.get(sandbox_id, {})
        for name in tool_names:
            sandbox_tools.pop(name, None)
        logger.info("tools_unregistered", sandbox_id=sandbox_id, plugin=plugin_name, tools=tool_names)

    def get_tools(self, sandbox_id: str) -> list["AgentTool"]:
        """Get all registered tools for a sandbox."""
        return list(self._tools.get(sandbox_id, {}).values())

    def get_tool(self, sandbox_id: str, tool_name: str) -> "AgentTool | None":
        return self._tools.get(sandbox_id, {}).get(tool_name)

    def get_tool_names(self, sandbox_id: str) -> list[str]:
        return list(self._tools.get(sandbox_id, {}).keys())

    def get_tools_for_plugin(self, sandbox_id: str, plugin_name: str) -> list[str]:
        return self._plugin_tools.get(sandbox_id, {}).get(plugin_name, [])

    def clear_sandbox(self, sandbox_id: str) -> None:
        self._tools.pop(sandbox_id, None)
        self._plugin_tools.pop(sandbox_id, None)

    # Event handlers — wired to EventBus at startup
    async def on_plugin_installed(self, event: "SandboxEvent") -> None:
        if event.event_type != "plugin.installed":
            return
        tools = event.data.get("tools", [])
        if tools and event.plugin_name:
            await self.register_tools(event.sandbox_id, event.plugin_name, tools)

    async def on_plugin_removed(self, event: "SandboxEvent") -> None:
        if event.event_type != "plugin.removed":
            return
        if event.plugin_name:
            await self.unregister_tools(event.sandbox_id, event.plugin_name)
