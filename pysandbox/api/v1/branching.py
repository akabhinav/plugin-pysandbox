"""Branching endpoints — fork a sandbox into a new one with copied state."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pysandbox.engine.branching import SandboxBranchError

router = APIRouter(prefix="/v1/sandboxes", tags=["branching"])


class BranchRequest(BaseModel):
    new_name: str
    owner_id: str = "default"
    copy_data: bool = True
    tags: dict[str, str] | None = None


@router.post("/{sandbox_id}/branch")
async def branch_sandbox(sandbox_id: str, req: BranchRequest, request: Request):
    """Create a new sandbox forked from this one.

    The new sandbox gets a fresh network + DNS zone + credentials, but
    starts with a copy of the source's plugin volume data (unless
    `copy_data=false`). The source sandbox is briefly paused during the
    copy so the captured state isn't torn.
    """
    brancher = getattr(request.app.state, "brancher", None)
    if brancher is None:
        raise HTTPException(status_code=503, detail="Brancher not initialized")
    try:
        return await brancher.branch(
            sandbox_id,
            new_name=req.new_name,
            owner_id=req.owner_id,
            copy_data=req.copy_data,
            tags=req.tags,
        )
    except SandboxBranchError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
