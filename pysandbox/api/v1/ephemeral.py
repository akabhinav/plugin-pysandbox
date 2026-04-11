"""Ephemeral sandbox endpoints — zero-config URL launcher.

A GET-based `/v1/spin` lets you paste a URL into a browser or Slack and
get back a short-lived sandbox. The body-less GET form deliberately
accepts query params only, so the call works from a plain link:

    GET /v1/spin?stack=microservices&ttl=1800
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from pysandbox.engine.ephemeral import (
    PRESET_STACKS,
    EphemeralSandboxLauncher,
)

router = APIRouter(prefix="/v1", tags=["ephemeral"])


class SpinRequest(BaseModel):
    """POST body variant — for clients that prefer JSON to query strings."""

    stack: str | None = None
    plugins: list[str] | None = None
    ttl_seconds: int | None = None
    name: str | None = None


def _launcher(request: Request) -> EphemeralSandboxLauncher:
    launcher = getattr(request.app.state, "ephemeral_launcher", None)
    if launcher is None:
        raise HTTPException(
            status_code=503, detail="Ephemeral launcher not initialized",
        )
    return launcher


@router.get("/spin")
async def spin_get(
    request: Request,
    stack: str | None = Query(None, description="Preset name or +-joined plugin list"),
    ttl: int | None = Query(None, description="TTL in seconds (default 1800, max 3600)"),
    name: str | None = Query(None),
):
    """Launch an ephemeral sandbox from a GET URL.

    Example: `/v1/spin?stack=microservices&ttl=1200`
    """
    launcher = _launcher(request)
    try:
        return await launcher.launch_from_request(
            stack=stack,
            ttl_seconds=ttl,
            name=name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spin")
async def spin_post(req: SpinRequest, request: Request):
    """Launch an ephemeral sandbox from a JSON body.

    Mirrors GET `/v1/spin` but accepts explicit plugin lists — useful for
    programmatic clients that don't want to URL-encode a plugin list.
    """
    launcher = _launcher(request)
    try:
        return await launcher.launch_from_request(
            stack=req.stack,
            plugins=req.plugins,
            ttl_seconds=req.ttl_seconds,
            name=req.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spin/presets")
async def list_presets():
    """List the curated preset stack names available for `?stack=`."""
    return {
        "presets": {k: list(v) for k, v in PRESET_STACKS.items()},
    }
