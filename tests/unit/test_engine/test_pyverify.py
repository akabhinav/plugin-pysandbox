"""Tests for the pyverify declarative runner."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.pyverify import (
    PyVerifyRunner,
    PyVerifySpec,
    parse_spec,
)


# ── Spec parsing ─────────────────────────────────────────────────────────

class TestParseSpec:
    def test_minimum_valid_spec(self):
        spec = parse_spec({
            "name": "smoke",
            "scenarios": [
                {"name": "s1", "steps": [{"tool": "sql_query", "args": {"query": "SELECT 1"}}]},
            ],
        })
        assert spec.name == "smoke"
        assert len(spec.scenarios) == 1
        assert spec.scenarios[0].steps[0].tool == "sql_query"

    def test_missing_tool_is_rejected(self):
        with pytest.raises(ValueError, match="missing required 'tool'"):
            parse_spec({"scenarios": [{"name": "s", "steps": [{"args": {}}]}]})

    def test_empty_steps_list_is_rejected(self):
        with pytest.raises(ValueError, match="at least one step"):
            parse_spec({"scenarios": [{"name": "s", "steps": []}]})

    def test_non_dict_root_rejected(self):
        with pytest.raises(ValueError):
            parse_spec("not a dict")  # type: ignore[arg-type]

    def test_scenarios_list_must_be_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            parse_spec({"scenarios": "oops"})

    def test_all_expectations_are_captured(self):
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {
                            "tool": "sql_query",
                            "args": {"query": "SELECT 1"},
                            "expect_no_error": True,
                            "expect_contains": "1",
                            "expect_matches": r"^\d",
                            "timeout_seconds": 10,
                        },
                    ],
                },
            ],
        })
        step = spec.scenarios[0].steps[0]
        assert step.expect_no_error is True
        assert step.expect_contains == "1"
        assert step.expect_matches == r"^\d"
        assert step.timeout_seconds == 10

    def test_stack_field_pulled_through(self):
        spec = parse_spec({"stack": ["postgres", "redis"], "scenarios": []})
        assert spec.stack == ["postgres", "redis"]


# ── Runner behavior ──────────────────────────────────────────────────────

def _registry_with_tools(tool_outputs: dict[str, str]):
    """Build a MagicMock AgentToolRegistry that returns the given outputs."""
    registry = MagicMock()

    def make_tool(name):
        tool_mock = MagicMock()
        tool_mock.handler = AsyncMock(return_value=tool_outputs.get(name, "ok"))
        return tool_mock

    registry.get_tool = MagicMock(side_effect=lambda sid, name: (
        make_tool(name) if name in tool_outputs else None
    ))
    return registry


class TestRunnerPass:
    @pytest.mark.asyncio
    async def test_single_passing_step(self):
        registry = _registry_with_tools({"sql_query": "1\n"})
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {
                            "tool": "sql_query",
                            "args": {"query": "SELECT 1"},
                            "expect_contains": "1",
                        },
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert result.success
        assert result.total == 1
        assert result.passed == 1

    @pytest.mark.asyncio
    async def test_multiple_steps_all_pass(self):
        registry = _registry_with_tools({
            "sql_execute": "INSERT 0 1",
            "sql_query": "ABC",
        })
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {"tool": "sql_execute", "args": {"statement": "INSERT ..."}, "expect_no_error": True},
                        {"tool": "sql_query", "args": {"query": "SELECT sku"}, "expect_contains": "ABC"},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert result.success
        assert len(result.steps) == 2

    @pytest.mark.asyncio
    async def test_no_assertions_counts_as_pass(self):
        registry = _registry_with_tools({"sql_execute": "CREATE TABLE"})
        spec = parse_spec({
            "scenarios": [
                {"name": "s", "steps": [{"tool": "sql_execute", "args": {"statement": "CREATE TABLE x(a)"}}]},
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert result.success


class TestRunnerFail:
    @pytest.mark.asyncio
    async def test_unknown_tool_fails_with_clear_message(self):
        registry = _registry_with_tools({})
        spec = parse_spec({
            "scenarios": [{"name": "s", "steps": [{"tool": "ghost", "args": {}}]}],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert not result.success
        assert "not registered" in result.steps[0].message

    @pytest.mark.asyncio
    async def test_expect_contains_failure(self):
        registry = _registry_with_tools({"sql_query": "different"})
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {
                            "tool": "sql_query",
                            "args": {},
                            "expect_contains": "ABC",
                        },
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert not result.success
        assert "expect_contains" in result.steps[0].message

    @pytest.mark.asyncio
    async def test_expect_no_error_trips_on_error_marker(self):
        registry = _registry_with_tools({"sql_execute": "ERROR: syntax near 'foo'"})
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {
                            "tool": "sql_execute",
                            "args": {},
                            "expect_no_error": True,
                        },
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert not result.success
        assert "expect_no_error" in result.steps[0].message

    @pytest.mark.asyncio
    async def test_expect_equals_strict(self):
        registry = _registry_with_tools({"redis_get": "ABC\n"})
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {"tool": "redis_get", "args": {}, "expect_equals": "ABC"},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        # strip on both sides means "ABC\n" == "ABC"
        assert result.success

    @pytest.mark.asyncio
    async def test_expect_matches_regex(self):
        registry = _registry_with_tools({"sql_query": "total: 42 rows"})
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {"tool": "sql_query", "args": {}, "expect_matches": r"\d+ rows"},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert result.success

    @pytest.mark.asyncio
    async def test_first_failure_stops_scenario(self):
        registry = _registry_with_tools({
            "sql_query": "nope",
            "redis_get": "never_reached",
        })
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {"tool": "sql_query", "args": {}, "expect_contains": "ABC"},
                        {"tool": "redis_get", "args": {}, "expect_contains": "never"},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        # Only the first step ran.
        assert len(result.steps) == 1
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_continue_on_failure_runs_every_step(self):
        registry = _registry_with_tools({
            "sql_query": "nope",
            "redis_get": "ok",
        })
        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "continue_on_failure": True,
                    "steps": [
                        {"tool": "sql_query", "args": {}, "expect_contains": "ABC"},
                        {"tool": "redis_get", "args": {}, "expect_contains": "ok"},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert len(result.steps) == 2
        assert result.passed == 1
        assert result.failed == 1


class TestRunnerTimeout:
    @pytest.mark.asyncio
    async def test_tool_timeout_caught(self):
        registry = MagicMock()
        slow_tool = MagicMock()

        async def slow_handler(args):
            await asyncio.sleep(10)
            return "never"

        slow_tool.handler = slow_handler
        registry.get_tool = MagicMock(return_value=slow_tool)

        spec = parse_spec({
            "scenarios": [
                {
                    "name": "s",
                    "steps": [
                        {"tool": "slow", "args": {}, "timeout_seconds": 1},
                    ],
                },
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        assert not result.success
        assert result.steps[0].error == "timeout"


class TestResultShape:
    @pytest.mark.asyncio
    async def test_to_dict_round_trips(self):
        registry = _registry_with_tools({"sql_query": "1"})
        spec = parse_spec({
            "scenarios": [
                {"name": "s", "steps": [{"tool": "sql_query", "args": {}, "expect_contains": "1"}]},
            ],
        })
        result = await PyVerifyRunner(registry).run("sb-1", spec)
        d = result.to_dict()
        assert d["success"] is True
        assert d["total"] == 1
        assert d["sandbox_id"] == "sb-1"
        assert "steps" in d
