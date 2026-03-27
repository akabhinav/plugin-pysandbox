"""Live resource monitoring and health dashboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/v1/monitoring", tags=["monitoring"])


@router.get("/resources/{sandbox_id}")
async def get_resource_usage(sandbox_id: str, request: Request):
    """Get live resource stats for all containers in a sandbox."""
    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instances = await instance_repo.list_instances(sandbox_id)
    if not instances:
        raise HTTPException(status_code=404, detail="No instances found")

    stats = []
    for inst in instances:
        cid = inst.get("container_id")
        if not cid:
            continue
        container_stats = await docker.get_container_stats(cid)
        container_stats["plugin_name"] = inst.get("plugin_name", "unknown")
        container_stats["plugin_id"] = inst.get("plugin_id", "unknown")
        stats.append(container_stats)

    return {"sandbox_id": sandbox_id, "stats": stats, "container_count": len(stats)}


@router.get("/health/{sandbox_id}")
async def get_health_dashboard(sandbox_id: str, request: Request):
    """Get health status for all plugins in a sandbox."""
    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instances = await instance_repo.list_instances(sandbox_id)
    results = []
    for inst in instances:
        cid = inst.get("container_id")
        status = "unknown"
        if cid:
            status = await docker.get_container_status(cid)
        results.append({
            "plugin_name": inst.get("plugin_name"),
            "plugin_id": inst.get("plugin_id"),
            "container_id": cid,
            "status": status,
            "version": inst.get("version"),
            "installed_at": inst.get("installed_at"),
        })

    healthy = sum(1 for r in results if r["status"] == "healthy")
    return {
        "sandbox_id": sandbox_id,
        "plugins": results,
        "total": len(results),
        "healthy": healthy,
        "unhealthy": len(results) - healthy,
    }


@router.get("/logs/{sandbox_id}/{plugin_name}")
async def get_plugin_logs(sandbox_id: str, plugin_name: str, request: Request, tail: int = 100):
    """Get recent logs for a specific plugin container."""
    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instance = await instance_repo.get_instance(sandbox_id, plugin_name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    cid = instance.get("container_id")
    if not cid:
        raise HTTPException(status_code=404, detail="No container for this plugin")

    logs = await docker.get_logs(cid, tail=tail)
    return {"plugin_name": plugin_name, "logs": logs, "tail": tail}
