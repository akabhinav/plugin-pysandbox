"""Activity timeline endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/v1/timeline", tags=["timeline"])


async def _get_sandbox_or_404(sandbox_id: str, request: Request):
    engine = request.app.state.sandbox_engine
    sandbox = await engine.get(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return sandbox


@router.get("/{sandbox_id}")
async def get_timeline(
    sandbox_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    event_type: str | None = None,
    severity: str | None = None,
):
    """Get activity timeline for a sandbox."""
    await _get_sandbox_or_404(sandbox_id, request)
    timeline = request.app.state.activity_timeline
    entries = timeline.get_timeline(
        sandbox_id, limit=limit, offset=offset,
        event_type=event_type, severity=severity,
    )
    total = timeline.get_total(sandbox_id)
    return {"entries": entries, "total": total, "limit": limit, "offset": offset}


@router.post("/{sandbox_id}")
async def add_timeline_entry(sandbox_id: str, request: Request):
    """Manually add a timeline entry (e.g., user notes)."""
    await _get_sandbox_or_404(sandbox_id, request)
    body = await request.json()
    timeline = request.app.state.activity_timeline
    entry = timeline.record(
        sandbox_id=sandbox_id,
        event_type=body.get("event_type", "user.note"),
        description=body.get("description", ""),
        plugin_name=body.get("plugin_name"),
        metadata=body.get("metadata", {}),
        severity=body.get("severity", "info"),
    )
    return {"entry": entry}


@router.delete("/{sandbox_id}")
async def clear_timeline(sandbox_id: str, request: Request):
    """Clear all timeline entries for a sandbox."""
    await _get_sandbox_or_404(sandbox_id, request)
    timeline = request.app.state.activity_timeline
    timeline.clear(sandbox_id)
    return {"status": "cleared", "sandbox_id": sandbox_id}
