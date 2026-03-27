"""Sandbox export/import endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pysandbox.engine.sandbox_export import SandboxExporter

router = APIRouter(prefix="/v1/export", tags=["export"])


class ImportRequest(BaseModel):
    config: dict[str, Any]
    name_override: str | None = None
    owner_id: str = "default"


@router.get("/{sandbox_id}")
async def export_sandbox(sandbox_id: str, request: Request):
    """Export sandbox configuration as portable JSON."""
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    instances = await engine._plugins._repo.list_instances(sandbox_id)
    config = SandboxExporter.export_config(sandbox, instances)
    return config


@router.post("/import")
async def import_sandbox(req: ImportRequest, request: Request):
    """Import a sandbox from exported configuration."""
    errors = SandboxExporter.validate_import(req.config)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    parsed = SandboxExporter.import_config(req.config)
    if req.name_override:
        parsed["name"] = req.name_override

    engine = request.app.state.sandbox_engine
    try:
        sandbox = await engine.create(
            name=parsed["name"],
            owner_id=req.owner_id,
            plugins=parsed["plugins"],
            tags=parsed["tags"],
        )
        return {"sandbox": sandbox, "imported_plugins": len(parsed["plugins"])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_import(request: Request):
    """Validate an import config without creating anything."""
    body = await request.json()
    errors = SandboxExporter.validate_import(body)
    return {"valid": len(errors) == 0, "errors": errors}
