"""Interactive web terminal — execute commands in plugin containers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/terminal", tags=["terminal"])


class ExecRequest(BaseModel):
    command: str
    timeout: int = 30


@router.post("/{sandbox_id}/{plugin_name}")
async def exec_in_plugin(
    sandbox_id: str,
    plugin_name: str,
    req: ExecRequest,
    request: Request,
):
    """Execute a command inside a plugin container. Returns stdout."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instance = await instance_repo.get_instance(sandbox_id, plugin_name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    cid = instance.get("container_id")
    if not cid:
        raise HTTPException(status_code=404, detail="No container for this plugin")

    try:
        output = await docker.exec_in_container(cid, req.command)
        return {
            "plugin_name": plugin_name,
            "command": req.command,
            "output": output,
            "status": "completed",
        }
    except Exception as e:
        return {
            "plugin_name": plugin_name,
            "command": req.command,
            "output": str(e),
            "status": "error",
        }


@router.get("/{sandbox_id}")
async def list_terminals(sandbox_id: str, request: Request):
    """List available plugin containers for terminal access."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    instance_repo = request.app.state.plugin_instance_repo
    instances = await instance_repo.list_instances(sandbox_id)
    return {
        "terminals": [
            {
                "plugin_name": inst.get("plugin_name"),
                "plugin_id": inst.get("plugin_id"),
                "container_id": inst.get("container_id", "")[:12],
                "status": inst.get("status"),
            }
            for inst in instances
            if inst.get("container_id")
        ],
    }
