"""Chaos injection endpoints.

Every endpoint returns the in-memory ChaosInjection record so clients can
correlate a later `reset` with what they injected. The chaos engine is
stored on app.state, just like sandbox_engine.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/chaos", tags=["chaos"])


async def _invoke_chaos(fn: Callable[[], Awaitable[Any]]) -> Any:
    """Run a chaos engine call and translate errors into clean HTTPExceptions.

    - `ValueError` from the engine (unknown plugin / missing container) → 404
    - Any other exception (e.g. docker.errors.APIError when the kernel
      doesn't support a feature like cgroup freezer) → 500 with the
      underlying message, so UI users see a useful error instead of a
      blank "Internal Server Error".
    """
    try:
        return await fn()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        # Squash the message to keep logs sane but still useful.
        raise HTTPException(status_code=500, detail=f"chaos op failed: {e}"[:500])


class KillRequest(BaseModel):
    plugin_name: str
    after_seconds: float = 0.0


class PauseRequest(BaseModel):
    plugin_name: str


class LatencyRequest(BaseModel):
    plugin_name: str
    delay_ms: int = Field(..., gt=0, le=60_000)
    jitter_ms: int = Field(0, ge=0, le=60_000)


class LossRequest(BaseModel):
    plugin_name: str
    loss_percent: float = Field(..., gt=0, le=100)


class CPUThrottleRequest(BaseModel):
    plugin_name: str
    cpus: float = Field(..., gt=0, le=32)


class MemoryThrottleRequest(BaseModel):
    plugin_name: str
    memory_mb: int = Field(..., gt=0, le=65536)


def _engine(request: Request):
    engine = getattr(request.app.state, "chaos_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Chaos engine not initialized — restart pysandbox",
        )
    return engine


async def _ensure_sandbox(request: Request, sandbox_id: str) -> None:
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")


@router.get("/{sandbox_id}")
async def list_active_chaos(sandbox_id: str, request: Request):
    """List every chaos effect currently active on this sandbox."""
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return {"sandbox_id": sandbox_id, "injections": await engine.list_active(sandbox_id)}


@router.post("/{sandbox_id}/kill")
async def chaos_kill(sandbox_id: str, req: KillRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.kill(
        sandbox_id, req.plugin_name, after_seconds=req.after_seconds,
    ))


@router.post("/{sandbox_id}/pause")
async def chaos_pause(sandbox_id: str, req: PauseRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.pause(sandbox_id, req.plugin_name))


@router.post("/{sandbox_id}/unpause")
async def chaos_unpause(sandbox_id: str, req: PauseRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.unpause(sandbox_id, req.plugin_name))


@router.post("/{sandbox_id}/latency")
async def chaos_latency(sandbox_id: str, req: LatencyRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.latency(
        sandbox_id, req.plugin_name, delay_ms=req.delay_ms, jitter_ms=req.jitter_ms,
    ))


@router.post("/{sandbox_id}/loss")
async def chaos_loss(sandbox_id: str, req: LossRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.packet_loss(
        sandbox_id, req.plugin_name, loss_percent=req.loss_percent,
    ))


@router.post("/{sandbox_id}/cpu-throttle")
async def chaos_cpu(sandbox_id: str, req: CPUThrottleRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.cpu_throttle(
        sandbox_id, req.plugin_name, cpus=req.cpus,
    ))


@router.post("/{sandbox_id}/memory-throttle")
async def chaos_mem(sandbox_id: str, req: MemoryThrottleRequest, request: Request):
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await _invoke_chaos(lambda: engine.memory_throttle(
        sandbox_id, req.plugin_name, memory_mb=req.memory_mb,
    ))


@router.post("/{sandbox_id}/reset")
async def chaos_reset(sandbox_id: str, request: Request):
    """Roll back every chaos effect on the sandbox."""
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    return await engine.reset(sandbox_id)
