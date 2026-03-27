"""Plugin install/remove/list endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/sandboxes/{sandbox_id}/plugins", tags=["plugins"])


class InstallPluginRequest(BaseModel):
    plugin_id: str
    name: str | None = None
    version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    expose: bool = False


@router.post("")
async def install_plugin(sandbox_id: str, req: InstallPluginRequest, request: Request):
    """Install a plugin into a sandbox."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    plugin_name = req.name or req.plugin_id
    connection = await engine._plugins.install(
        sandbox_id=sandbox_id,
        docker_network=sandbox["docker_network"],
        dns_zone=sandbox["dns_zone"],
        plugin_id=req.plugin_id,
        plugin_name=plugin_name,
        version=req.version,
        config=req.config,
        expose=req.expose,
    )
    return {
        "status": "installed",
        "plugin_id": req.plugin_id,
        "plugin_name": plugin_name,
        "dns_name": connection.dns_name,
        "host_port": connection.host_port,
        "host_ports": connection.host_ports,
    }


@router.get("")
async def list_plugins(sandbox_id: str, request: Request):
    """List installed plugins and their health."""
    repo = request.app.state.plugin_instance_repo
    instances = await repo.list_instances(sandbox_id)
    return {"plugins": instances}


@router.get("/{plugin_name}")
async def get_plugin_instance(sandbox_id: str, plugin_name: str, request: Request):
    """Get details of an installed plugin."""
    repo = request.app.state.plugin_instance_repo
    instance = await repo.get_instance(sandbox_id, plugin_name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found in sandbox")
    return {"plugin": instance}


@router.delete("/{plugin_name}")
async def remove_plugin(sandbox_id: str, plugin_name: str, request: Request):
    """Remove a plugin from a sandbox."""
    engine = request.app.state.sandbox_engine
    await engine._plugins.remove(sandbox_id, plugin_name)
    return {"status": "removed", "plugin_name": plugin_name}


@router.post("/{plugin_name}/restart")
async def restart_plugin(sandbox_id: str, plugin_name: str, request: Request):
    """Restart a plugin container."""
    repo = request.app.state.plugin_instance_repo
    docker = request.app.state.docker_runtime
    instance = await repo.get_instance(sandbox_id, plugin_name)
    if not instance or not instance.get("container_id"):
        raise HTTPException(status_code=404, detail="Plugin not found")
    await docker.stop(instance["container_id"])
    await docker.start(instance["container_id"])
    return {"status": "restarted", "plugin_name": plugin_name}


@router.get("/{plugin_name}/tools")
async def get_plugin_tools(sandbox_id: str, plugin_name: str, request: Request):
    """List agent tools provided by this plugin."""
    tool_registry = request.app.state.tool_registry
    tool_names = tool_registry.get_tools_for_plugin(sandbox_id, plugin_name)
    return {"tools": tool_names}
