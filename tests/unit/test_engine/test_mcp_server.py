"""Tests for the pysandbox MCP server surface."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.mcp_server import (
    ERR_INVALID_PARAMS,
    ERR_INVALID_REQUEST,
    ERR_METHOD_NOT_FOUND,
    ERR_TOOL_NOT_FOUND,
    McpSession,
)


def _tool(name, description="desc", schema=None):
    t = MagicMock()
    t.name = name
    t.description = description
    t.parameters = schema or {"type": "object", "properties": {}}
    t.handler = AsyncMock(return_value="ok")
    return t


@pytest.fixture
def registry():
    reg = MagicMock()
    tools = [
        _tool("sql_query", "Run SQL SELECT"),
        _tool("redis_get", "Read a Redis key"),
    ]
    reg.get_tools = MagicMock(return_value=tools)

    def get_tool(sid, name):
        for t in tools:
            if t.name == name:
                return t
        return None

    reg.get_tool = MagicMock(side_effect=get_tool)
    return reg


@pytest.fixture
def session(registry):
    return McpSession(registry, sandbox_id="sb-abc")


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_returns_server_info(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"clientInfo": {"name": "cursor"}},
        })
        assert resp["id"] == 1
        result = resp["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["serverInfo"]["name"] == "pysandbox"
        assert "tools" in result["capabilities"]

    @pytest.mark.asyncio
    async def test_initialized_notification_has_no_response(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        assert resp is None


class TestToolsList:
    @pytest.mark.asyncio
    async def test_tools_list_maps_parameters_to_input_schema(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        })
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert len(tools) == 2
        # MCP uses `inputSchema`, not `parameters`.
        assert "inputSchema" in tools[0]
        assert "parameters" not in tools[0]
        assert tools[0]["name"] == "sql_query"


class TestToolsCall:
    @pytest.mark.asyncio
    async def test_tool_call_returns_text_content(self, session, registry):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "sql_query", "arguments": {"query": "SELECT 1"}},
        })
        result = resp["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "ok"

    @pytest.mark.asyncio
    async def test_tool_call_unknown_tool_errors(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "ghost", "arguments": {}},
        })
        assert "error" in resp
        assert resp["error"]["code"] == ERR_TOOL_NOT_FOUND
        # Surface the actual available tools so the model can recover.
        assert "available" in resp["error"]["data"]

    @pytest.mark.asyncio
    async def test_tool_call_missing_name_is_invalid_params(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {},
        })
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_tool_call_invalid_arguments_type(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "sql_query", "arguments": "not a dict"},
        })
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_tool_handler_exception_returns_is_error_content(
        self, session, registry,
    ):
        # Replace the handler so it throws.
        failing_tool = _tool("sql_query")
        failing_tool.handler = AsyncMock(side_effect=RuntimeError("boom"))
        registry.get_tool = MagicMock(return_value=failing_tool)

        resp = await session.handle({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "sql_query", "arguments": {}},
        })
        # Tool-level errors are returned inside result (isError=true) so
        # the model can see them and recover — NOT as JSON-RPC errors.
        result = resp["result"]
        assert result["isError"] is True
        assert "boom" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_tool_call_timeout_returns_jsonrpc_error(self, session, registry):
        slow_tool = _tool("sql_query")

        async def slow_handler(args):
            await asyncio.sleep(5)

        slow_tool.handler = slow_handler
        registry.get_tool = MagicMock(return_value=slow_tool)
        session._default_timeout = 0.01

        resp = await session.handle({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "sql_query", "arguments": {}},
        })
        assert "error" in resp
        assert "timed out" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_dict_tool_result_is_json_serialized(self, session, registry):
        dict_tool = _tool("sql_query")
        dict_tool.handler = AsyncMock(return_value={"rows": [1, 2, 3]})
        registry.get_tool = MagicMock(return_value=dict_tool)

        resp = await session.handle({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "sql_query", "arguments": {}},
        })
        text = resp["result"]["content"][0]["text"]
        assert '"rows"' in text


class TestErrors:
    @pytest.mark.asyncio
    async def test_unknown_method(self, session):
        resp = await session.handle({
            "jsonrpc": "2.0", "id": 10, "method": "bogus",
        })
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_missing_method(self, session):
        resp = await session.handle({"jsonrpc": "2.0", "id": 11})
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_non_dict_message(self, session):
        resp = await session.handle("not a dict")  # type: ignore[arg-type]
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_ping_returns_empty_result(self, session):
        resp = await session.handle({"jsonrpc": "2.0", "id": 12, "method": "ping"})
        assert resp["result"] == {}
