"""Fork-from-production endpoints.

Three-stage flow:
  1. POST `/v1/fork/{sandbox_id}/introspect` — read schema from source
  2. POST `/v1/fork/{sandbox_id}/plan` — build a fork plan + preview PII columns
  3. POST `/v1/fork/{sandbox_id}/apply` — execute the plan on a target sandbox

The stages are split so CI / UI can surface the PII detection results
to a human before synthesizing/writing anything.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pysandbox.engine.fork_production import (
    ForkFromProductionEngine,
    ForkPlan,
    TableSpec,
)

router = APIRouter(prefix="/v1/fork", tags=["fork"])


class IntrospectRequest(BaseModel):
    tables: list[str] = Field(..., min_length=1)


class PlanRequest(BaseModel):
    tables: list[dict]  # TableSpec dicts round-tripped from /introspect
    rows_per_table: int = Field(50, ge=1, le=100_000)
    seed: int = 42


class ApplyRequest(BaseModel):
    target_sandbox_id: str
    plan: dict


def _engine(request: Request) -> ForkFromProductionEngine:
    return ForkFromProductionEngine(request.app.state.tool_registry)


async def _ensure_sandbox(request: Request, sandbox_id: str) -> None:
    sb = await request.app.state.sandbox_engine.get(sandbox_id)
    if not sb:
        raise HTTPException(status_code=404, detail="Sandbox not found")


def _table_specs_from_dicts(raw: list[dict]) -> list[TableSpec]:
    """Rebuild TableSpec objects from the JSON-friendly plan shape."""
    specs = []
    for t in raw:
        from pysandbox.engine.fork_production import ColumnSpec
        cols = [
            ColumnSpec(
                name=c["name"],
                sql_type=c.get("type") or c.get("sql_type") or "text",
                nullable=bool(c.get("nullable", True)),
                pii_kind=c.get("pii_kind"),
            ).classify()
            for c in t.get("columns", [])
        ]
        specs.append(TableSpec(name=t["name"], columns=cols))
    return specs


@router.post("/{sandbox_id}/introspect")
async def introspect(sandbox_id: str, req: IntrospectRequest, request: Request):
    """Read the schema for a set of tables from the source sandbox.

    Returns a list of TableSpecs ready to be passed to /plan.
    """
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    try:
        specs = await engine.introspect(sandbox_id, req.tables)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    plan = engine.plan(specs)
    return plan.to_dict()


@router.post("/{sandbox_id}/plan")
async def build_plan(sandbox_id: str, req: PlanRequest, request: Request):
    """Build a ForkPlan + preview PII columns without running anything.

    This is where a UI surfaces "we found these PII columns, click
    confirm to proceed" — it's deliberately a read-only preview so the
    caller can reject a plan that's still too risky.
    """
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    specs = _table_specs_from_dicts(req.tables)
    plan = engine.plan(specs, rows_per_table=req.rows_per_table, seed=req.seed)
    return plan.to_dict()


@router.post("/{sandbox_id}/preview")
async def preview_statements(
    sandbox_id: str, req: PlanRequest, request: Request,
):
    """Return the INSERT statements we'd apply, without executing them.

    Useful as a dry-run for review or for piping into a file the user
    inspects before applying.
    """
    await _ensure_sandbox(request, sandbox_id)
    engine = _engine(request)
    specs = _table_specs_from_dicts(req.tables)
    plan = engine.plan(specs, rows_per_table=req.rows_per_table, seed=req.seed)
    rendered = engine.render_statements(plan)
    return {
        "tables": [
            {"name": name, "statement_count": len(stmts), "statements": stmts}
            for name, stmts in rendered
        ],
    }


@router.post("/apply")
async def apply_plan(req: ApplyRequest, request: Request):
    """Apply a plan to a target sandbox.

    `plan` is the dict returned by /plan or /introspect. The target
    sandbox must have an sql_execute agent tool (i.e. a postgres or
    mysql plugin installed) — we check up-front so the caller gets a
    clear error rather than 50 individual failures.
    """
    await _ensure_sandbox(request, req.target_sandbox_id)
    engine = _engine(request)
    specs = _table_specs_from_dicts(req.plan.get("tables", []))
    plan_obj = ForkPlan(
        tables=specs,
        rows_per_table=int(req.plan.get("rows_per_table", 50)),
        seed=int(req.plan.get("seed", 42)),
    )
    try:
        return await engine.apply(req.target_sandbox_id, plan_obj)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
