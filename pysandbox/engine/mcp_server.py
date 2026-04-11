"""MCP-compatible surface over pysandbox's per-sandbox agent tool registry.

This module exposes the existing `AgentToolRegistry` as a Model Context
Protocol-style JSON-RPC surface, so language-model clients (Claude Desktop,
Cursor, etc.) can list and call pysandbox tools natively.

We implement the subset of MCP 2025-06-18 that matters for tool use:

  * `initialize`                 — handshake + capability negotiation
  * `tools/list`                 — return the tool catalog for a sandbox
  * `tools/call`                 — invoke a named tool with arguments

The transport is intentionally decoupled: `McpSession.handle(message)`
takes a JSON-RPC request dict and returns a response dict. A FastAPI
endpoint wraps this over HTTP POST; anything that can pipe JSON can
reuse the same object.

Why not a full MCP server library? pysandbox already owns the tool
registry, authentication, and lifecycle — bolting on a library would
add a dependency to do less than 100 lines of glue. This module is
drop-in replaceable with an official MCP SDK later if that matters.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


# ── JSON-RPC helpers ─────────────────────────────────────────────────────

JSONRPC_VERSION = "2.0"

# Error codes (standard JSON-RPC + a few MCP-specific ones).
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_TOOL_NOT_FOUND = -32001
ERR_TOOL_EXEC_FAILED = -32002
ERR_SANDBOX_NOT_FOUND = -32003


def _rpc_ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _rpc_err(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": err}


# ── Session ──────────────────────────────────────────────────────────────

@dataclass
class McpServerInfo:
    name: str = "pysandbox"
    version: str = "1.0.0"


class McpSession:
    """One MCP session, scoped to a single sandbox.

    Sessions are created per connection so that the tool catalog reflects
    the sandbox's current plugin set and so tool calls are automatically
    routed to the right tool handler.

    The session is deliberately stateless beyond `initialized`: if the
    sandbox changes (plugin installed / removed) between calls, the
    next `tools/list` reflects that automatically because it queries
    the registry live.
    """

    def __init__(
        self,
        tool_registry,
        sandbox_id: str,
        *,
        server_info: McpServerInfo | None = None,
        default_tool_timeout: float = 120.0,
    ) -> None:
        self._registry = tool_registry
        self._sandbox_id = sandbox_id
        self._server_info = server_info or McpServerInfo()
        self._default_timeout = default_tool_timeout
        self._initialized = False
        self._client_info: dict[str, Any] | None = None

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    # ── handler ────────────────────────────────────────────────────────

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch a JSON-RPC request. Returns a response dict or None
        for notifications (messages without an `id`)."""
        if not isinstance(message, dict):
            return _rpc_err(None, ERR_INVALID_REQUEST, "message must be an object")

        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if not method or not isinstance(method, str):
            return _rpc_err(request_id, ERR_INVALID_REQUEST, "missing method")

        # Notifications (no id) get handled but not replied to.
        is_notification = "id" not in message

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "initialized" or method == "notifications/initialized":
                # Client confirming init; no response expected.
                self._initialized = True
                return None
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "ping":
                result = {}
            elif method == "shutdown":
                result = {}
            else:
                return _rpc_err(
                    request_id, ERR_METHOD_NOT_FOUND, f"unknown method {method!r}",
                )
        except _McpError as e:
            return _rpc_err(request_id, e.code, e.message, e.data)
        except Exception as e:
            logger.exception("mcp_handler_unhandled", method=method)
            return _rpc_err(request_id, ERR_INTERNAL, str(e))

        if is_notification:
            return None
        return _rpc_ok(request_id, result)

    # ── method implementations ─────────────────────────────────────────

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self._client_info = params.get("clientInfo")
        # Advertise only what we actually implement.
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": self._server_info.name,
                "version": self._server_info.version,
            },
            "instructions": (
                f"You are connected to a pysandbox sandbox ({self._sandbox_id}). "
                "Use the listed tools to interact with the plugins installed "
                "in this sandbox. Tools appear/disappear as plugins are "
                "installed or removed."
            ),
        }

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        tools = self._registry.get_tools(self._sandbox_id)
        # MCP wants `inputSchema`, not `parameters` — translate.
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.parameters,
                }
                for t in tools
            ],
        }

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not name or not isinstance(name, str):
            raise _McpError(ERR_INVALID_PARAMS, "params.name (tool name) is required")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise _McpError(ERR_INVALID_PARAMS, "params.arguments must be an object")

        tool = self._registry.get_tool(self._sandbox_id, name)
        if tool is None:
            raise _McpError(
                ERR_TOOL_NOT_FOUND,
                f"tool {name!r} not registered for sandbox {self._sandbox_id}",
                data={"available": [t.name for t in self._registry.get_tools(self._sandbox_id)]},
            )

        try:
            raw = await asyncio.wait_for(
                tool.handler(arguments),
                timeout=self._default_timeout,
            )
        except asyncio.TimeoutError:
            raise _McpError(
                ERR_TOOL_EXEC_FAILED,
                f"tool {name!r} timed out after {self._default_timeout}s",
            )
        except Exception as e:
            # Per MCP spec, tool-level errors go in the result with isError,
            # not as JSON-RPC errors, so the model can see them and recover.
            return {
                "content": [
                    {"type": "text", "text": f"Error calling {name}: {e}"},
                ],
                "isError": True,
            }

        # Normalize the tool output into MCP's content format.
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }


class _McpError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
