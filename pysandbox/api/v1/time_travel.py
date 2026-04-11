"""Time-travel endpoints — snapshot, list, rewind, delete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pysandbox.engine.time_travel import TimeTravelError

router = APIRouter(prefix="/v1/time-travel", tags=["time-travel"])


class CaptureRequest(BaseModel):
    label: str | None = None


class AutoCaptureRequest(BaseModel):
    interval_seconds: int = Field(300, ge=30, le=3600)


def _engine(request: Request):
    engine = getattr(request.app.state, "time_travel_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Time-travel engine not initialized")
    return engine


async def _ensure_sandbox(request: Request, sandbox_id: str):
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return sb


@router.post("/{sandbox_id}/capture")
async def capture(sandbox_id: str, req: CaptureRequest, request: Request):
    """Take a new snapshot of every plugin volume in this sandbox."""
    await _ensure_sandbox(request, sandbox_id)
    try:
        return await _engine(request).capture(sandbox_id, label=req.label)
    except TimeTravelError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{sandbox_id}")
async def list_snapshots(sandbox_id: str, request: Request):
    """Return all snapshots for this sandbox, newest first."""
    await _ensure_sandbox(request, sandbox_id)
    return {
        "sandbox_id": sandbox_id,
        "snapshots": _engine(request).list_snapshots(sandbox_id),
    }


@router.post("/{sandbox_id}/rewind/{snapshot_id}")
async def rewind(sandbox_id: str, snapshot_id: str, request: Request):
    """Restore the sandbox to the state captured in `snapshot_id`."""
    await _ensure_sandbox(request, sandbox_id)
    try:
        return await _engine(request).rewind(sandbox_id, snapshot_id)
    except TimeTravelError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{sandbox_id}/{snapshot_id}")
async def delete_snapshot(sandbox_id: str, snapshot_id: str, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    removed = await _engine(request).delete_snapshot(sandbox_id, snapshot_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"deleted": snapshot_id}


@router.post("/{sandbox_id}/auto/start")
async def start_auto_capture(sandbox_id: str, req: AutoCaptureRequest, request: Request):
    """Start periodic background snapshots for this sandbox."""
    await _ensure_sandbox(request, sandbox_id)
    await _engine(request).start_auto_capture(sandbox_id, req.interval_seconds)
    return {"status": "started", "interval_seconds": req.interval_seconds}


@router.post("/{sandbox_id}/auto/stop")
async def stop_auto_capture(sandbox_id: str, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    stopped = await _engine(request).stop_auto_capture(sandbox_id)
    return {"status": "stopped" if stopped else "not_running"}
