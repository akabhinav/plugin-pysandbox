"""Recorder endpoints — capture tool calls and export them as runbooks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/recorder", tags=["recorder"])


class StartRequest(BaseModel):
    name: str | None = None
    preserve: bool = False


class AnnotateRequest(BaseModel):
    note: str


def _recorder(request: Request):
    rec = getattr(request.app.state, "recorder", None)
    if rec is None:
        raise HTTPException(
            status_code=503, detail="Recorder not initialized — restart pysandbox",
        )
    return rec


async def _ensure_sandbox(request: Request, sandbox_id: str) -> None:
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")


@router.post("/{sandbox_id}/start")
async def start_recording(sandbox_id: str, req: StartRequest, request: Request):
    """Begin capturing every agent tool call on this sandbox."""
    await _ensure_sandbox(request, sandbox_id)
    session = _recorder(request).start(sandbox_id, name=req.name, preserve=req.preserve)
    return {
        "sandbox_id": session.sandbox_id,
        "name": session.name,
        "started_at": session.started_at,
        "active": session.active,
    }


@router.post("/{sandbox_id}/stop")
async def stop_recording(sandbox_id: str, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    session = _recorder(request).stop(sandbox_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active recording")
    return {
        "sandbox_id": session.sandbox_id,
        "stopped_at": session.stopped_at,
        "call_count": len(session.calls),
    }


@router.get("/{sandbox_id}")
async def get_recording(sandbox_id: str, request: Request):
    """Return the in-memory recording, or an idle stub if none exists.

    Returning a stub rather than 404 prevents the UI from showing
    a spurious error toast every time the Recorder tab loads on a
    sandbox that hasn't started a recording yet.
    """
    await _ensure_sandbox(request, sandbox_id)
    data = _recorder(request).to_dict(sandbox_id)
    if data is None:
        return {
            "sandbox_id": sandbox_id,
            "name": None,
            "started_at": None,
            "stopped_at": None,
            "active": False,
            "call_count": 0,
            "calls": [],
        }
    return data


@router.delete("/{sandbox_id}")
async def discard_recording(sandbox_id: str, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    _recorder(request).discard(sandbox_id)
    return {"status": "discarded", "sandbox_id": sandbox_id}


@router.post("/{sandbox_id}/annotate")
async def annotate_last_call(sandbox_id: str, req: AnnotateRequest, request: Request):
    """Attach a human-readable note to the most recent captured call.

    Meant for mid-debugging context: "this is the step that fixed it".
    The note gets surfaced when the recording is exported as markdown
    or as a pyverify spec (becomes the step name).
    """
    await _ensure_sandbox(request, sandbox_id)
    ok = _recorder(request).annotate_last(sandbox_id, req.note)
    if not ok:
        raise HTTPException(status_code=404, detail="No captured calls to annotate")
    return {"status": "annotated"}


@router.get("/{sandbox_id}/export/pyverify")
async def export_as_pyverify(sandbox_id: str, request: Request):
    """Export recording as a pyverify spec dict (JSON)."""
    await _ensure_sandbox(request, sandbox_id)
    spec = _recorder(request).to_pyverify_spec(sandbox_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="No recording for this sandbox")
    return spec


@router.get("/{sandbox_id}/export/markdown")
async def export_as_markdown(sandbox_id: str, request: Request):
    """Export recording as a markdown runbook (text/markdown)."""
    await _ensure_sandbox(request, sandbox_id)
    md = _recorder(request).to_markdown(sandbox_id)
    if md is None:
        raise HTTPException(status_code=404, detail="No recording for this sandbox")
    return Response(content=md, media_type="text/markdown")
