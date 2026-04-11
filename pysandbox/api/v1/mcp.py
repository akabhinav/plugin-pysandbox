"""MCP HTTP transport — POST /v1/mcp/{sandbox_id}.

This is a thin HTTP veneer over `McpSession.handle()`. A proper MCP
client would use stdio or SSE; HTTP is the simplest thing we can ship
today, and it's easy to upgrade later because the session object is
transport-agnostic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pysandbox.engine.mcp_server import McpServerInfo, McpSession

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


class McpMessage(BaseModel):
    """Accept a bare JSON-RPC message — no extra wrapper."""

    jsonrpc: str = "2.0"
    method: str
    id: Any = None
    params: dict[str, Any] | None = None


async def _ensure_sandbox(request: Request, sandbox_id: str) -> None:
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")


@router.post("/{sandbox_id}")
async def mcp_rpc(sandbox_id: str, request: Request):
    """Handle one MCP JSON-RPC request for the given sandbox.

    This endpoint is stateless — each POST is a complete request. A
    long-running MCP client should reuse sessions via SSE/WebSocket;
    this path is aimed at simple curl-level exploration and CI.
    """
    await _ensure_sandbox(request, sandbox_id)
    body = await request.json()
    session = McpSession(
        tool_registry=request.app.state.tool_registry,
        sandbox_id=sandbox_id,
        server_info=McpServerInfo(name="pysandbox", version="1.0.0"),
    )
    response = await session.handle(body)
    if response is None:
        # Notifications get a 204 No Content.
        return {}
    return response


@router.get("/{sandbox_id}/info")
async def mcp_info(sandbox_id: str, request: Request):
    """Return human-readable info about this sandbox's MCP surface.

    Handy for debugging Claude Desktop / Cursor integration without
    having to go through the full JSON-RPC handshake.
    """
    await _ensure_sandbox(request, sandbox_id)
    tools = request.app.state.tool_registry.get_tools(sandbox_id)
    return {
        "sandbox_id": sandbox_id,
        "endpoint": f"/v1/mcp/{sandbox_id}",
        "protocol_version": "2025-06-18",
        "tool_count": len(tools),
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ],
    }
