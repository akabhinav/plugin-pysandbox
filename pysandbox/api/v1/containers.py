"""Container management endpoints — list and remove Docker containers."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/containers", tags=["containers"])


class RemoveRequest(BaseModel):
    container_ids: list[str]


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
