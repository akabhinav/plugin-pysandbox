"""Tests for the agent tool registry."""

import pytest

from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.engine.event_bus import SandboxEvent
from pysandbox.plugin.base import AgentTool


def _make_tool(name: str) -> AgentTool:
    async def handler(params):
        return f"{name} result"
    return AgentTool(name=name, description=f"Test {name}", parameters={}, handler=handler)


class TestAgentToolRegistry:
    @pytest.mark.asyncio
    async def test_register_and_get_tools(self, tool_registry):
        """Registered tools are retrievable."""
        tools = [_make_tool("sql_query"), _make_tool("sql_execute")]
        await tool_registry.register_tools("sb1", "postgres", tools)

        result = tool_registry.get_tools("sb1")
        assert len(result) == 2
        names = {t.name for t in result}
        assert names == {"sql_query", "sql_execute"}

    @pytest.mark.asyncio
    async def test_unregister_tools(self, tool_registry):
        """Unregistered tools are removed."""
        tools = [_make_tool("redis_get"), _make_tool("redis_set")]
        await tool_registry.register_tools("sb1", "redis", tools)
        await tool_registry.unregister_tools("sb1", "redis")

        assert len(tool_registry.get_tools("sb1")) == 0

    @pytest.mark.asyncio
    async def test_multiple_plugins(self, tool_registry):
        """Tools from multiple plugins coexist."""
        await tool_registry.register_tools("sb1", "postgres", [_make_tool("sql_query")])
        await tool_registry.register_tools("sb1", "redis", [_make_tool("redis_get")])

        assert len(tool_registry.get_tools("sb1")) == 2

    @pytest.mark.asyncio
    async def test_unregister_only_removes_own_tools(self, tool_registry):
        """Unregistering one plugin doesn't affect another's tools."""
        await tool_registry.register_tools("sb1", "postgres", [_make_tool("sql_query")])
        await tool_registry.register_tools("sb1", "redis", [_make_tool("redis_get")])
        await tool_registry.unregister_tools("sb1", "redis")

        tools = tool_registry.get_tools("sb1")
        assert len(tools) == 1
        assert tools[0].name == "sql_query"

    @pytest.mark.asyncio
    async def test_sandboxes_isolated(self, tool_registry):
        """Different sandboxes have independent tool sets."""
        await tool_registry.register_tools("sb1", "postgres", [_make_tool("sql_query")])
        await tool_registry.register_tools("sb2", "redis", [_make_tool("redis_get")])

        sb1_tools = tool_registry.get_tools("sb1")
        sb2_tools = tool_registry.get_tools("sb2")

        assert len(sb1_tools) == 1
        assert sb1_tools[0].name == "sql_query"
        assert len(sb2_tools) == 1
        assert sb2_tools[0].name == "redis_get"

    @pytest.mark.asyncio
    async def test_get_tool_by_name(self, tool_registry):
        """Individual tools can be retrieved by name."""
        await tool_registry.register_tools("sb1", "pg", [_make_tool("sql_query")])
        tool = tool_registry.get_tool("sb1", "sql_query")
        assert tool is not None
        assert tool.name == "sql_query"

    @pytest.mark.asyncio
    async def test_get_nonexistent_tool(self, tool_registry):
        """Getting a nonexistent tool returns None."""
        assert tool_registry.get_tool("sb1", "nope") is None

    @pytest.mark.asyncio
    async def test_clear_sandbox(self, tool_registry):
        """Clearing a sandbox removes all its tools."""
        await tool_registry.register_tools("sb1", "pg", [_make_tool("sql_query")])
        tool_registry.clear_sandbox("sb1")
        assert len(tool_registry.get_tools("sb1")) == 0

    @pytest.mark.asyncio
    async def test_get_tools_for_plugin(self, tool_registry):
        """Can retrieve tool names for a specific plugin."""
        await tool_registry.register_tools("sb1", "postgres", [_make_tool("sql_query"), _make_tool("sql_execute")])
        names = tool_registry.get_tools_for_plugin("sb1", "postgres")
        assert set(names) == {"sql_query", "sql_execute"}

    @pytest.mark.asyncio
    async def test_event_handler_install(self, tool_registry):
        """on_plugin_installed event registers tools."""
        tools = [_make_tool("test_tool")]
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.installed",
            plugin_name="test-plugin",
            data={"tools": tools},
        )
        await tool_registry.on_plugin_installed(event)
        assert len(tool_registry.get_tools("sb1")) == 1

    @pytest.mark.asyncio
    async def test_event_handler_remove(self, tool_registry):
        """on_plugin_removed event unregisters tools."""
        await tool_registry.register_tools("sb1", "test-plugin", [_make_tool("test_tool")])
        event = SandboxEvent(
            sandbox_id="sb1",
            event_type="plugin.removed",
            plugin_name="test-plugin",
        )
        await tool_registry.on_plugin_removed(event)
        assert len(tool_registry.get_tools("sb1")) == 0
