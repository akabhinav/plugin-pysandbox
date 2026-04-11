"""Live resource monitoring and health dashboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pysandbox.engine.cost_meter import CostMeter

router = APIRouter(prefix="/v1/monitoring", tags=["monitoring"])


@router.get("/resources/{sandbox_id}")
async def get_resource_usage(sandbox_id: str, request: Request):
    """Get live resource stats for all containers in a sandbox."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instances = await instance_repo.list_instances(sandbox_id)
    if not instances:
        return {"sandbox_id": sandbox_id, "stats": [], "container_count": 0}

    stats = []
    errors = []
    for inst in instances:
        cid = inst.get("container_id")
        if not cid:
            continue
        try:
            container_stats = await docker.get_container_stats(cid)
            container_stats["plugin_name"] = inst.get("plugin_name", "unknown")
            container_stats["plugin_id"] = inst.get("plugin_id", "unknown")
            stats.append(container_stats)
        except Exception as e:
            errors.append({
                "plugin_name": inst.get("plugin_name", "unknown"),
                "container_id": cid[:12],
                "error": str(e),
            })

    result = {"sandbox_id": sandbox_id, "stats": stats, "container_count": len(stats)}
    if errors:
        result["errors"] = errors
    return result


@router.get("/health/{sandbox_id}")
async def get_health_dashboard(sandbox_id: str, request: Request):
    """Get health status for all plugins in a sandbox."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    instances = await instance_repo.list_instances(sandbox_id)
    results = []
    for inst in instances:
        cid = inst.get("container_id")
        status = "unknown"
        if cid:
            try:
                status = await docker.get_container_status(cid)
            except Exception:
                status = "unreachable"
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

    logs = await docker.get_logs(cid, tail=tail)
    return {"plugin_name": plugin_name, "logs": logs, "tail": tail}


@router.get("/cost/{sandbox_id}")
async def get_sandbox_cost(sandbox_id: str, request: Request):
    """Estimate cost + CO₂ footprint for a single sandbox.

    Uses live container stats when available; falls back to "assume 100%
    of quota" otherwise. The returned `tip` field surfaces obvious waste
    (e.g. multi-day sandbox at <10% CPU).
    """
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo
    instances = await instance_repo.list_instances(sandbox_id)

    stats = []
    for inst in instances:
        cid = inst.get("container_id")
        if not cid:
            continue
        try:
            cs = await docker.get_container_stats(cid)
            cs["container_id"] = cid
            stats.append(cs)
        except Exception:
            # Missing stats means we'll fall back to the "assumed" path
            # in CostMeter — still useful, just less precise.
            pass

    meter: CostMeter = getattr(request.app.state, "cost_meter", None) or CostMeter()
    return meter.estimate_sandbox(sandbox, instances, stats)


@router.get("/cost")
async def get_fleet_cost(request: Request):
    """Fleet-wide cost rollup across every sandbox the engine knows about.

    Sorted by USD descending so the top expense jumps out at a glance.
    """
    engine = request.app.state.sandbox_engine
    docker = request.app.state.docker_runtime
    instance_repo = request.app.state.plugin_instance_repo

    sandboxes = await engine.list_all()
    items = []
    for sb in sandboxes:
        if sb.get("status") == "destroyed":
            continue
        instances = await instance_repo.list_instances(sb["id"])
        stats = []
        for inst in instances:
            cid = inst.get("container_id")
            if not cid:
                continue
            try:
                cs = await docker.get_container_stats(cid)
                cs["container_id"] = cid
                stats.append(cs)
            except Exception:
                pass
        items.append({"sandbox": sb, "instances": instances, "stats": stats})

    meter: CostMeter = getattr(request.app.state, "cost_meter", None) or CostMeter()
    return meter.estimate_fleet(items)
