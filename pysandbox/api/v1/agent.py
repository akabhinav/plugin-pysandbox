"""Agent execution and management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/sandboxes/{sandbox_id}/agent", tags=["agent"])


class ExecuteTaskRequest(BaseModel):
    task: str
    timeout: int = 300


@router.post("/execute")
async def execute_agent_task(sandbox_id: str, req: ExecuteTaskRequest, request: Request):
    """Execute a task via the sandbox agent."""
    agent = request.app.state.agent_runtime
    if not agent.is_running(sandbox_id):
        raise HTTPException(status_code=400, detail="Agent not running for this sandbox")
    return {
        "status": "submitted",
        "sandbox_id": sandbox_id,
        "task": req.task,
    }


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
