"""Container and network management endpoints — list, remove, and cleanup Docker resources."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/containers", tags=["containers"])


class RemoveRequest(BaseModel):
    container_ids: list[str]


class RemoveNetworksRequest(BaseModel):
    network_ids: list[str]


@router.get("")
async def list_containers(request: Request):
    """List all pysandbox-managed Docker containers."""
    docker = request.app.state.docker_runtime
    containers = await docker.list_managed_containers()
    return {"containers": containers, "total": len(containers)}


@router.post("/remove")
async def remove_containers(req: RemoveRequest, request: Request):
    """Force remove selected containers."""
    docker = request.app.state.docker_runtime
    removed = await docker.force_remove_containers(req.container_ids)
    return {"removed": removed, "count": len(removed)}


@router.get("/networks")
async def list_networks(request: Request):
    """List all pysandbox-managed Docker networks."""
    docker = request.app.state.docker_runtime
    networks = await docker.list_managed_networks()
    return {"networks": networks, "total": len(networks)}


@router.post("/networks/prune")
async def prune_networks(request: Request):
    """Remove all pysandbox networks with no running containers."""
    docker = request.app.state.docker_runtime
    removed = await docker.prune_managed_networks()
    return {"removed": removed, "count": len(removed)}


@router.post("/networks/remove")
async def remove_networks(req: RemoveNetworksRequest, request: Request):
    """Force remove selected networks (disconnects containers first)."""
    docker = request.app.state.docker_runtime
    removed = await docker.force_remove_networks(req.network_ids)
    return {"removed": removed, "count": len(removed)}


@router.post("/cleanup")
async def full_cleanup(request: Request):
    """Remove ALL pysandbox containers, volumes, and networks. Nuclear option.

    Also marks every sandbox as 'destroyed' in the repo so the dashboard
    reflects the actual state.
    """
    docker = request.app.state.docker_runtime
    result = await docker.full_cleanup()

    # Mark all sandboxes as destroyed in the repo
    engine = request.app.state.sandbox_engine
    all_sandboxes = await engine.list_all()
    destroyed_count = 0
    for sb in all_sandboxes:
        if sb.get("status") not in ("destroyed",):
            await engine._repo.update_status(sb["id"], "destroyed")
            destroyed_count += 1
    result["sandboxes_marked_destroyed"] = destroyed_count

    return result
