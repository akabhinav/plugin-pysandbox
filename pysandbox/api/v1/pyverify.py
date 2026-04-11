"""pyverify endpoints — run a declarative YAML verification spec."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pysandbox.engine.pyverify import PyVerifyRunner, parse_spec

router = APIRouter(prefix="/v1/pyverify", tags=["pyverify"])


class RunSpecRequest(BaseModel):
    """Inline spec submitted as a dict. Use this path when the client
    already has the YAML parsed (e.g. a CI runner)."""

    spec: dict[str, Any]


class RunYamlRequest(BaseModel):
    """Raw YAML text. We parse it server-side so clients don't need PyYAML."""

    yaml: str


async def _resolve_sandbox(request: Request, sandbox_id: str):
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    if sb.get("status") != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Sandbox must be running (is '{sb.get('status')}')",
        )
    return sb


@router.post("/{sandbox_id}/run")
async def run_spec(sandbox_id: str, req: RunSpecRequest, request: Request):
    """Run a pyverify spec expressed as a parsed dict."""
    await _resolve_sandbox(request, sandbox_id)
    try:
        spec = parse_spec(req.spec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid spec: {e}")

    runner = PyVerifyRunner(request.app.state.tool_registry)
    result = await runner.run(sandbox_id, spec)
    return result.to_dict()


@router.post("/{sandbox_id}/run-yaml")
async def run_spec_yaml(sandbox_id: str, req: RunYamlRequest, request: Request):
    """Run a pyverify spec expressed as raw YAML text.

    Equivalent to `run`, but spares the client from needing a YAML parser.
    """
    await _resolve_sandbox(request, sandbox_id)
    import yaml
    try:
        data = yaml.safe_load(req.yaml) or {}
        spec = parse_spec(data)
    except (ValueError, yaml.YAMLError) as e:
        raise HTTPException(status_code=400, detail=f"invalid spec: {e}")

    runner = PyVerifyRunner(request.app.state.tool_registry)
    result = await runner.run(sandbox_id, spec)
    return result.to_dict()


@router.post("/validate")
async def validate_spec(req: RunSpecRequest):
    """Validate a pyverify spec without running it (for CI pre-commit hooks)."""
    try:
        spec = parse_spec(req.spec)
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    return {
        "valid": True,
        "name": spec.name,
        "stack": spec.stack,
        "scenario_count": len(spec.scenarios),
        "step_count": sum(len(s.steps) for s in spec.scenarios),
    }
