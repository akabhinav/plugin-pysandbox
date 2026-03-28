"""Bulk operations and batch API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/batch", tags=["batch"])


class BatchPauseRequest(BaseModel):
    sandbox_ids: list[str]


class BatchResumeRequest(BaseModel):
    sandbox_ids: list[str]


class BatchDestroyRequest(BaseModel):
    sandbox_ids: list[str]


class BatchPluginInstallRequest(BaseModel):
    sandbox_ids: list[str]
    plugin_id: str
    name: str | None = None
    version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    expose: bool = True


@router.post("/pause")
async def batch_pause(req: BatchPauseRequest, request: Request):
    """Pause multiple sandboxes at once."""
    engine = request.app.state.sandbox_engine
    results = {"succeeded": [], "failed": []}
    for sid in req.sandbox_ids:
        try:
            sandbox = await engine.get(sid)
            if not sandbox:
                results["failed"].append({"sandbox_id": sid, "error": "Not found"})
                continue
            if sandbox.get("status") != "running":
                results["failed"].append({"sandbox_id": sid, "error": f"Cannot pause: status is '{sandbox.get('status')}'"})
                continue
            await engine.pause(sid)
            results["succeeded"].append(sid)
        except Exception as e:
            results["failed"].append({"sandbox_id": sid, "error": str(e)})
    return results


@router.post("/resume")
async def batch_resume(req: BatchResumeRequest, request: Request):
    """Resume multiple sandboxes at once."""
    engine = request.app.state.sandbox_engine
    results = {"succeeded": [], "failed": []}
    for sid in req.sandbox_ids:
        try:
            sandbox = await engine.get(sid)
            if not sandbox:
                results["failed"].append({"sandbox_id": sid, "error": "Not found"})
                continue
            if sandbox.get("status") != "paused":
                results["failed"].append({"sandbox_id": sid, "error": f"Cannot resume: status is '{sandbox.get('status')}'"})
                continue
            await engine.resume(sid)
            results["succeeded"].append(sid)
        except Exception as e:
            results["failed"].append({"sandbox_id": sid, "error": str(e)})
    return results


@router.post("/destroy")
async def batch_destroy(req: BatchDestroyRequest, request: Request):
    """Destroy multiple sandboxes at once."""
    engine = request.app.state.sandbox_engine
    results = {"succeeded": [], "failed": []}
    for sid in req.sandbox_ids:
        try:
            sandbox = await engine.get(sid)
            if not sandbox:
                results["failed"].append({"sandbox_id": sid, "error": "Not found"})
                continue
            if sandbox.get("status") == "destroyed":
                results["failed"].append({"sandbox_id": sid, "error": "Already destroyed"})
                continue
            await engine.destroy(sid)
            results["succeeded"].append(sid)
        except Exception as e:
            results["failed"].append({"sandbox_id": sid, "error": str(e)})
    return results


@router.post("/install-plugin")
async def batch_install_plugin(req: BatchPluginInstallRequest, request: Request):
    """Install the same plugin into multiple sandboxes."""
    engine = request.app.state.sandbox_engine
    results = {"succeeded": [], "failed": []}
    for sid in req.sandbox_ids:
        try:
            sandbox = await engine.get(sid)
            if not sandbox:
                results["failed"].append({"sandbox_id": sid, "error": "Not found"})
                continue
            await engine._plugins.install(
                sandbox_id=sid,
                docker_network=sandbox["docker_network"],
                dns_zone=sandbox["dns_zone"],
                plugin_id=req.plugin_id,
                plugin_name=req.name or req.plugin_id,
                version=req.version,
                config=req.config,
                expose=req.expose,
            )
            results["succeeded"].append(sid)
        except Exception as e:
            results["failed"].append({"sandbox_id": sid, "error": str(e)})
    return results


@router.get("/status")
async def batch_status(request: Request, sandbox_ids: str = ""):
    """Get status for multiple sandboxes. Pass comma-separated IDs."""
    engine = request.app.state.sandbox_engine
    if not sandbox_ids:
        return {"sandboxes": []}

    ids = [s.strip() for s in sandbox_ids.split(",") if s.strip()]
    results = []
    for sid in ids:
        sandbox = await engine.get(sid)
        if sandbox:
            instances = await engine._plugins._repo.list_instances(sid)
            results.append({
                "sandbox_id": sid,
                "name": sandbox.get("name"),
                "status": sandbox.get("status"),
                "plugin_count": len(instances),
            })
    return {"sandboxes": results}
