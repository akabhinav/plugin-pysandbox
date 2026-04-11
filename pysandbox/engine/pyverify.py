"""pyverify — declarative verification runner driven by a YAML spec.

A `pyverify.yaml` file lets teams express their integration contract as a
sequence of steps run against a REAL pysandbox stack (not mocks). Unlike
the hardcoded `sandbox_verify.PLUGIN_CHECKS`, this is per-project: each
repo drops its own file in and gets it run in CI.

Shape of the YAML:

    name: "My service contract"
    stack:                       # optional — if omitted, run against an
      - postgres                 # existing sandbox
      - redis
      - kafka

    scenarios:
      - name: "Order checkout propagates"
        steps:
          - tool: sql_execute
            args: { statement: "CREATE TABLE orders(id serial, sku text)" }
            expect_no_error: true

          - tool: sql_execute
            args: { statement: "INSERT INTO orders(sku) VALUES ('ABC')" }

          - tool: sql_query
            args: { query: "SELECT sku FROM orders" }
            expect_contains: "ABC"

          - tool: redis_set
            args: { key: "last_order", value: "ABC" }

          - tool: redis_get
            args: { key: "last_order" }
            expect_equals: "ABC\\n"

Every `tool` name must be a registered agent tool in the target sandbox.
The runner looks them up via the existing AgentToolRegistry, so there's
one source of truth for what tools exist.

Supported expectations (all optional, combine freely):
  - expect_no_error:  bool — no common error markers in output
  - expect_contains:  str  — substring present (case-insensitive)
  - expect_equals:    str  — exact match (after strip)
  - expect_matches:   str  — regex match against the output
  - expect_empty:     bool — output empty / whitespace only
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


# ── Spec loader ──────────────────────────────────────────────────────────

@dataclass
class PyVerifyStep:
    """One tool invocation + its expectations."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    expect_no_error: bool = False
    expect_contains: str | None = None
    expect_equals: str | None = None
    expect_matches: str | None = None
    expect_empty: bool = False
    timeout_seconds: int = 60


@dataclass
class PyVerifyScenario:
    """A named sequence of steps. Stops at the first failure by default."""

    name: str
    steps: list[PyVerifyStep]
    continue_on_failure: bool = False


@dataclass
class PyVerifySpec:
    """Top-level YAML document."""

    name: str
    stack: list[str] = field(default_factory=list)
    scenarios: list[PyVerifyScenario] = field(default_factory=list)


def load_spec(path: str | Path) -> PyVerifySpec:
    """Parse a `pyverify.yaml` file into a PyVerifySpec dataclass tree."""
    import yaml
    text = Path(path).read_text()
    data = yaml.safe_load(text) or {}
    return parse_spec(data)


def parse_spec(data: dict[str, Any]) -> PyVerifySpec:
    """Parse a pre-loaded dict (e.g. from JSON) into a PyVerifySpec.

    Kept separate from load_spec so callers that already have the config
    as a dict (API clients posting JSON) don't have to go through YAML.
    Every known field is validated here so downstream code can trust
    the dataclasses.
    """
    if not isinstance(data, dict):
        raise ValueError("pyverify spec must be a mapping")

    name = data.get("name", "pyverify")
    stack = list(data.get("stack") or [])
    scenarios_raw = data.get("scenarios") or []
    if not isinstance(scenarios_raw, list):
        raise ValueError("`scenarios` must be a list")

    scenarios: list[PyVerifyScenario] = []
    for i, sc_raw in enumerate(scenarios_raw):
        if not isinstance(sc_raw, dict):
            raise ValueError(f"scenario {i} must be a mapping")
        sc_name = sc_raw.get("name", f"scenario {i+1}")
        steps_raw = sc_raw.get("steps") or []
        if not isinstance(steps_raw, list) or not steps_raw:
            raise ValueError(f"scenario '{sc_name}' must have at least one step")
        steps: list[PyVerifyStep] = []
        for j, st_raw in enumerate(steps_raw):
            if not isinstance(st_raw, dict):
                raise ValueError(f"scenario '{sc_name}' step {j} must be a mapping")
            if "tool" not in st_raw:
                raise ValueError(
                    f"scenario '{sc_name}' step {j}: missing required 'tool'",
                )
            steps.append(PyVerifyStep(
                tool=st_raw["tool"],
                args=dict(st_raw.get("args") or {}),
                name=st_raw.get("name"),
                expect_no_error=bool(st_raw.get("expect_no_error", False)),
                expect_contains=st_raw.get("expect_contains"),
                expect_equals=st_raw.get("expect_equals"),
                expect_matches=st_raw.get("expect_matches"),
                expect_empty=bool(st_raw.get("expect_empty", False)),
                timeout_seconds=int(st_raw.get("timeout_seconds", 60)),
            ))
        scenarios.append(PyVerifyScenario(
            name=sc_name,
            steps=steps,
            continue_on_failure=bool(sc_raw.get("continue_on_failure", False)),
        ))
    return PyVerifySpec(name=name, stack=stack, scenarios=scenarios)


# ── Validators ───────────────────────────────────────────────────────────

_ERROR_MARKERS = ["error", "exception", "fatal", "refused", "denied", "traceback"]


def _check_step(step: PyVerifyStep, output: str) -> tuple[bool, str]:
    """Evaluate every expectation on a step. All must pass for the step to pass."""
    messages = []

    if step.expect_no_error:
        lower = output.lower()
        for marker in _ERROR_MARKERS:
            if marker in lower and "0 error" not in lower:
                return False, f"expect_no_error: found '{marker}' in output"
        messages.append("no-error ✓")

    if step.expect_contains is not None:
        if step.expect_contains.lower() not in output.lower():
            return False, (
                f"expect_contains: {step.expect_contains!r} not in output"
            )
        messages.append(f"contains {step.expect_contains!r} ✓")

    if step.expect_equals is not None:
        if output.strip() != step.expect_equals.strip():
            return False, (
                f"expect_equals: got {output[:60]!r}, want {step.expect_equals!r}"
            )
        messages.append(f"equals {step.expect_equals!r} ✓")

    if step.expect_matches is not None:
        if not re.search(step.expect_matches, output):
            return False, f"expect_matches: {step.expect_matches!r} did not match"
        messages.append(f"matches /{step.expect_matches}/ ✓")

    if step.expect_empty:
        if output.strip():
            return False, f"expect_empty: got {output[:60]!r}"
        messages.append("empty ✓")

    if not messages:
        # No assertions at all — we treat tool success as pass (no exception
        # was raised). Useful for setup steps like DDL.
        return True, "ran"

    return True, ", ".join(messages)


# ── Runner ───────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    scenario: str
    step_index: int
    name: str
    tool: str
    passed: bool
    message: str
    duration_ms: int
    output: str = ""
    error: str | None = None


@dataclass
class PyVerifyResult:
    spec_name: str
    sandbox_id: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    duration_ms: int = 0
    steps: list[StepResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_name": self.spec_name,
            "sandbox_id": self.sandbox_id,
            "success": self.success,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "duration_ms": self.duration_ms,
            "steps": [
                {
                    "scenario": s.scenario,
                    "step_index": s.step_index,
                    "name": s.name,
                    "tool": s.tool,
                    "passed": s.passed,
                    "message": s.message,
                    "duration_ms": s.duration_ms,
                    "output": (s.output or "")[:500],
                    "error": s.error,
                }
                for s in self.steps
            ],
        }


class PyVerifyRunner:
    """Runs a PyVerifySpec against a sandbox, using its AgentToolRegistry.

    The runner doesn't manage the sandbox lifecycle — it assumes the
    sandbox already exists with the expected plugins installed. Callers
    that want fresh-stack execution should spin up the sandbox first
    (the top-level `stack:` field is advisory metadata for now).
    """

    def __init__(self, tool_registry) -> None:
        self._registry = tool_registry

    async def run(self, sandbox_id: str, spec: PyVerifySpec) -> PyVerifyResult:
        result = PyVerifyResult(spec_name=spec.name, sandbox_id=sandbox_id)
        overall_start = time.monotonic()

        for scenario in spec.scenarios:
            for idx, step in enumerate(scenario.steps):
                step_result = await self._run_step(sandbox_id, scenario, idx, step)
                result.steps.append(step_result)
                result.total += 1
                if step_result.passed:
                    result.passed += 1
                else:
                    result.failed += 1
                    if not scenario.continue_on_failure:
                        break

        result.duration_ms = int((time.monotonic() - overall_start) * 1000)
        return result

    async def _run_step(
        self, sandbox_id: str, scenario: PyVerifyScenario, idx: int, step: PyVerifyStep,
    ) -> StepResult:
        name = step.name or f"{scenario.name}[{idx}] {step.tool}"
        start = time.monotonic()

        tool = self._registry.get_tool(sandbox_id, step.tool)
        if tool is None:
            return StepResult(
                scenario=scenario.name,
                step_index=idx,
                name=name,
                tool=step.tool,
                passed=False,
                message=f"tool '{step.tool}' not registered",
                duration_ms=int((time.monotonic() - start) * 1000),
                error="unknown_tool",
            )

        try:
            output = await asyncio.wait_for(
                tool.handler(step.args),
                timeout=step.timeout_seconds,
            )
            output_str = output if isinstance(output, str) else str(output)
        except asyncio.TimeoutError:
            return StepResult(
                scenario=scenario.name, step_index=idx, name=name, tool=step.tool,
                passed=False, message=f"timeout after {step.timeout_seconds}s",
                duration_ms=int((time.monotonic() - start) * 1000),
                error="timeout",
            )
        except Exception as e:
            return StepResult(
                scenario=scenario.name, step_index=idx, name=name, tool=step.tool,
                passed=False, message=f"exception: {e}",
                duration_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )

        passed, message = _check_step(step, output_str)
        return StepResult(
            scenario=scenario.name,
            step_index=idx,
            name=name,
            tool=step.tool,
            passed=passed,
            message=message,
            duration_ms=int((time.monotonic() - start) * 1000),
            output=output_str,
        )
