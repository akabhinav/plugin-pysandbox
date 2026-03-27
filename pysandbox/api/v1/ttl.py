"""Sandbox TTL management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/ttl", tags=["ttl"])


class SetTTLRequest(BaseModel):
    ttl_seconds: int


@router.get("")
async def list_ttls(request: Request):
    """List all sandboxes with TTL configured."""
    ttl_manager = request.app.state.ttl_manager
    ttls = ttl_manager.list_ttls()
    return {"ttls": ttls, "total": len(ttls)}


@router.get("/{sandbox_id}")
async def get_ttl(sandbox_id: str, request: Request):
    """Get TTL info for a sandbox."""
    ttl_manager = request.app.state.ttl_manager
    info = ttl_manager.get_ttl(sandbox_id)
    if not info:
        raise HTTPException(status_code=404, detail="No TTL set for this sandbox")
    return info


@router.post("/{sandbox_id}")
async def set_ttl(sandbox_id: str, req: SetTTLRequest, request: Request):
    """Set or update TTL for a sandbox."""
    if req.ttl_seconds < 60:
        raise HTTPException(status_code=400, detail="TTL must be at least 60 seconds")
    ttl_manager = request.app.state.ttl_manager
    info = ttl_manager.set_ttl(sandbox_id, req.ttl_seconds)
    return info


@router.delete("/{sandbox_id}")
async def remove_ttl(sandbox_id: str, request: Request):
    """Remove TTL from a sandbox (make it permanent)."""
    ttl_manager = request.app.state.ttl_manager
    if not ttl_manager.remove_ttl(sandbox_id):
        raise HTTPException(status_code=404, detail="No TTL set for this sandbox")
    return {"status": "removed", "sandbox_id": sandbox_id}
