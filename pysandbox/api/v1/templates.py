"""Sandbox template endpoints — list, get, and create from templates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/templates", tags=["templates"])


class CreateFromTemplateRequest(BaseModel):
    name: str
    owner_id: str = "default"
    template_id: str = ""
    overrides: dict[str, Any] = Field(default_factory=dict)


class CustomTemplateRequest(BaseModel):
    id: str
    name: str
    description: str
    category: str = "custom"
    icon: str = "📦"
    plugins: list[dict[str, Any]]
    tags: dict[str, str] = Field(default_factory=dict)
    estimated_startup_seconds: int = 60


@router.get("")
async def list_templates(request: Request):
    """List all sandbox templates."""
    registry = request.app.state.template_registry
    templates = registry.list_all()
    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "icon": t.icon,
                "plugin_count": len(t.plugins),
                "plugins": [p["plugin_id"] for p in t.plugins],
                "tags": t.tags,
                "estimated_startup_seconds": t.estimated_startup_seconds,
            }
            for t in templates
        ],
        "total": len(templates),
    }


@router.get("/{template_id}")
async def get_template(template_id: str, request: Request):
    """Get template details including full plugin configs."""
    registry = request.app.state.template_registry
    template = registry.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "icon": template.icon,
        "plugins": template.plugins,
        "tags": template.tags,
        "estimated_startup_seconds": template.estimated_startup_seconds,
    }


@router.post("/launch")
async def launch_from_template(req: CreateFromTemplateRequest, request: Request):
    """Create a sandbox from a template."""
    registry = request.app.state.template_registry
    template = registry.get(req.template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{req.template_id}' not found")

    engine = request.app.state.sandbox_engine
    tags = {**template.tags, **req.overrides.get("tags", {})}

    try:
        sandbox = await engine.create(
            name=req.name,
            owner_id=req.owner_id,
            plugins=template.plugins,
            tags=tags,
        )
        return {"sandbox": sandbox, "template_id": template.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def register_custom_template(req: CustomTemplateRequest, request: Request):
    """Register a custom template."""
    from pysandbox.engine.templates import SandboxTemplate

    registry = request.app.state.template_registry
    template = SandboxTemplate(
        id=req.id,
        name=req.name,
        description=req.description,
        category=req.category,
        icon=req.icon,
        plugins=req.plugins,
        tags=req.tags,
        estimated_startup_seconds=req.estimated_startup_seconds,
    )
    registry.register(template)
    return {"status": "registered", "template_id": req.id}


@router.delete("/{template_id}")
async def unregister_template(template_id: str, request: Request):
    """Unregister a custom template."""
    registry = request.app.state.template_registry
    if not registry.unregister(template_id):
        raise HTTPException(status_code=404, detail="Template not found or is a builtin")
    return {"status": "removed", "template_id": template_id}
