"""Tests for agent context builder."""

import pytest

from pysandbox.agent.context_builder import AgentContextBuilder
from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.plugin.base import AgentTool


class TestAgentContextBuilder:
    @pytest.mark.asyncio
    async def test_build_empty_context(self, tool_registry):
        builder = AgentContextBuilder(tool_registry)
        ctx = builder.build("sb1", "my-sandbox", "abc.sandbox.local", [])

        assert "my-sandbox" in ctx
        assert "abc.sandbox.local" in ctx
        assert "Total tools available: 0" in ctx

    @pytest.mark.asyncio
    async def test_build_with_plugins(self, tool_registry):
        """Context includes installed plugins and their tools."""
        async def handler(p): return ""
        tools = [AgentTool("sql_query", "Query SQL", {}, handler)]
        await tool_registry.register_tools("sb1", "postgres", tools)

        builder = AgentContextBuilder(tool_registry)
        plugins = [{"plugin_id": "postgres", "plugin_name": "postgres"}]
        ctx = builder.build("sb1", "my-sandbox", "abc.sandbox.local", plugins)

        assert "postgres" in ctx
        assert "sql_query" in ctx
        assert "Total tools available: 1" in ctx
