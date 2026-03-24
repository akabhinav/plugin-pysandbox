"""Agent execution, tool invocation, and management endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/sandboxes/{sandbox_id}/agent", tags=["agent"])


class ExecuteTaskRequest(BaseModel):
    task: str
    timeout: int = 300


class ToolCallRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/execute")
async def execute_agent_task(sandbox_id: str, req: ExecuteTaskRequest, request: Request):
    """Execute a task via the sandbox agent.

    Parses the task as a tool invocation if it matches a registered tool name.
    Format: "tool_name arg1=val1 arg2=val2" or just pass a tool name to list its schema.
    """
    tool_registry = request.app.state.tool_registry
    agent = request.app.state.agent_runtime

    if not agent.is_running(sandbox_id):
        raise HTTPException(status_code=400, detail="Agent not running for this sandbox")

    # Check if task matches a tool name directly
    parts = req.task.strip().split(None, 1)
    tool_name = parts[0] if parts else ""
    tool = tool_registry.get_tool(sandbox_id, tool_name)

    if tool:
        # Parse remaining text as JSON params or key=value pairs
        params = {}
        if len(parts) > 1:
            raw = parts[1].strip()
            try:
                params = json.loads(raw)
            except json.JSONDecodeError:
                # Try key=value parsing
                for kv in raw.split():
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        params[k] = v

        try:
            result = await asyncio.wait_for(tool.handler(params), timeout=req.timeout)
            return {
                "status": "completed",
                "sandbox_id": sandbox_id,
                "tool": tool_name,
                "result": result,
            }
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "sandbox_id": sandbox_id,
                "tool": tool_name,
                "error": f"Tool execution timed out after {req.timeout}s",
            }
        except Exception as e:
            return {
                "status": "error",
                "sandbox_id": sandbox_id,
                "tool": tool_name,
                "error": str(e),
            }

    # No matching tool — return available tools
    tools = tool_registry.get_tools(sandbox_id)
    return {
        "status": "error",
        "sandbox_id": sandbox_id,
        "error": f"Unknown tool '{tool_name}'. Use one of the available tools.",
        "available_tools": [t.name for t in tools],
    }


@router.post("/tools/{tool_name}/execute")
async def execute_tool(sandbox_id: str, tool_name: str, req: ToolCallRequest, request: Request):
    """Execute a specific tool by name with given parameters."""
    tool_registry = request.app.state.tool_registry
    tool = tool_registry.get_tool(sandbox_id, tool_name)

    if not tool:
        available = tool_registry.get_tool_names(sandbox_id)
        raise HTTPException(
            status_code=404,
            detail={"error": f"Tool '{tool_name}' not found", "available_tools": available},
        )

    try:
        result = await asyncio.wait_for(tool.handler(req.params), timeout=120)
        return {
            "status": "completed",
            "tool": tool_name,
            "sandbox_id": sandbox_id,
            "result": result,
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Tool '{tool_name}' execution timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {e}")


@router.get("/status")
async def get_agent_status(sandbox_id: str, request: Request):
    """Get agent health and current task."""
    agent = request.app.state.agent_runtime
    return {
        "running": agent.is_running(sandbox_id),
        "container_id": agent.get_container_id(sandbox_id),
    }


@router.get("/tools")
async def get_agent_tools(sandbox_id: str, request: Request):
    """List all tools registered across all plugins."""
    tool_registry = request.app.state.tool_registry
    tools = tool_registry.get_tools(sandbox_id)
    return {
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ],
        "total": len(tools),
    }


@router.post("/stop")
async def stop_agent(sandbox_id: str, request: Request):
    """Stop the current agent task."""
    agent = request.app.state.agent_runtime
    await agent.stop(sandbox_id)
    return {"status": "stopped"}
