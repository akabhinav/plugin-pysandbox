"""Sandbox CRUD endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/sandboxes", tags=["sandboxes"])


class PluginSpec(BaseModel):
    plugin_id: str
    name: str | None = None
    version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    expose: bool = False


class CreateSandboxRequest(BaseModel):
    name: str
    owner_id: str = "default"
    org_id: str | None = None
    plugins: list[PluginSpec] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


@router.post("")
async def create_sandbox(req: CreateSandboxRequest, request: Request):
    """Create a new sandbox with optional initial plugins."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.create(
        name=req.name,
        owner_id=req.owner_id,
        org_id=req.org_id,
        plugins=[p.model_dump() for p in req.plugins],
        tags=req.tags,
    )
    return {"sandbox": _sanitize(sandbox)}


@router.get("")
async def list_sandboxes(request: Request):
    """List all sandboxes."""
    engine = request.app.state.sandbox_engine
    sandboxes = await engine.list_all()
    return {"sandboxes": [_sanitize(s) for s in sandboxes]}


@router.get("/{sandbox_id}")
async def get_sandbox(sandbox_id: str, request: Request):
    """Get sandbox details including installed plugins."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Get installed plugins
    instances = await engine._plugins._repo.list_instances(sandbox_id)
    return {"sandbox": _sanitize(sandbox), "plugins": instances}


@router.delete("/{sandbox_id}")
async def destroy_sandbox(sandbox_id: str, request: Request):
    """Destroy a sandbox and all its plugins."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    await engine.destroy(sandbox_id)
    return {"status": "destroyed", "sandbox_id": sandbox_id}


@router.post("/{sandbox_id}/pause")
async def pause_sandbox(sandbox_id: str, request: Request):
    """Pause a sandbox (stop containers, retain volumes)."""
    engine = request.app.state.sandbox_engine
    await engine.pause(sandbox_id)
    return {"status": "paused", "sandbox_id": sandbox_id}


@router.post("/{sandbox_id}/resume")
async def resume_sandbox(sandbox_id: str, request: Request):
    """Resume a paused sandbox."""
    engine = request.app.state.sandbox_engine
    await engine.resume(sandbox_id)
    return {"status": "running", "sandbox_id": sandbox_id}


@router.get("/{sandbox_id}/env")
async def get_sandbox_env(sandbox_id: str, request: Request):
    """Get all injected env vars (secrets redacted)."""
    env_injector = request.app.state.env_injector
    return {"env": env_injector.get_redacted(sandbox_id)}


@router.get("/{sandbox_id}/dns")
async def get_sandbox_dns(sandbox_id: str, request: Request):
    """Get DNS zone entries."""
    dns_manager = request.app.state.dns_manager
    return {"records": dns_manager.get_records(sandbox_id)}


def _sanitize(sandbox: dict) -> dict:
    """Remove internal fields from sandbox response."""
    safe = dict(sandbox)
    safe.pop("spec", None)
    return safe
