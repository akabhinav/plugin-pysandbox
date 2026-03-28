"""Sandbox verification, seeding, and quickstart endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pysandbox.engine.sandbox_quickstart import get_quickstart, list_quickstarts

router = APIRouter(prefix="/v1/sandboxes/{sandbox_id}", tags=["verify"])


@router.post("/verify")
async def verify_sandbox(sandbox_id: str, request: Request):
    """Run smoke tests on all plugins and cross-plugin connectivity.

    Executes real queries/commands through agent tools to verify
    the sandbox actually works, not just that containers are healthy.
    """
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if sandbox.get("status") != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot verify sandbox in '{sandbox.get('status')}' state — must be running",
        )

    verifier = request.app.state.sandbox_verifier
    # Detect template_id from tags
    template_id = sandbox.get("tags", {}).get("template")
    result = await verifier.verify(sandbox_id, template_id=template_id)
    return result.to_dict()


@router.post("/seed")
async def seed_sandbox(sandbox_id: str, request: Request):
    """Pre-load sample data into all installed plugins.

    Creates realistic tables, records, topics, and cache entries
    so developers have data to work with immediately.
    """
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if sandbox.get("status") != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot seed sandbox in '{sandbox.get('status')}' state — must be running",
        )

    seeder = request.app.state.sandbox_seeder
    result = await seeder.seed(sandbox_id)
    return result.to_dict()


@router.get("/quickstart")
async def get_sandbox_quickstart(sandbox_id: str, request: Request):
    """Get the interactive quickstart guide for this sandbox's template.

    Returns step-by-step instructions with pre-filled tool parameters
    that developers can execute one at a time.
    """
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    template_id = sandbox.get("tags", {}).get("template")
    if not template_id:
        raise HTTPException(
            status_code=404,
            detail="No quickstart available — sandbox was not created from a template",
        )

    qs = get_quickstart(template_id)
    if not qs:
        raise HTTPException(
            status_code=404,
            detail=f"No quickstart defined for template '{template_id}'",
        )

    return qs.to_dict()


# ── Non-sandbox-scoped endpoints ─────────────────────────────────────────────

quickstart_router = APIRouter(prefix="/v1/quickstarts", tags=["quickstarts"])


@quickstart_router.get("")
async def list_all_quickstarts():
    """List all available quickstart guides."""
    guides = list_quickstarts()
    return {"quickstarts": guides, "total": len(guides)}
