"""Tests for fork-from-production engine."""

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.fork_production import (
    ColumnSpec,
    ForkFromProductionEngine,
    TableSpec,
    detect_pii_kind,
    parse_psql_describe,
    render_inserts,
    synthesize,
    synthesize_for_type,
)


# ── PII detection ──────────────────────────────────────────────────────

class TestPiiDetection:
    def test_email_detected(self):
        assert detect_pii_kind("email") == "email"
        assert detect_pii_kind("user_email") == "email"
        assert detect_pii_kind("email_verified") == "email"

    def test_phone_detected(self):
        assert detect_pii_kind("phone_number") == "phone"
        assert detect_pii_kind("mobile") == "phone"

    def test_ssn_detected(self):
        assert detect_pii_kind("ssn") == "ssn"
        assert detect_pii_kind("social_security_number") == "ssn"

    def test_credit_card_detected(self):
        assert detect_pii_kind("credit_card") == "credit_card"
        assert detect_pii_kind("card_number") == "credit_card"

    def test_name_detected(self):
        assert detect_pii_kind("first_name") == "first_name"
        assert detect_pii_kind("last_name") == "last_name"
        assert detect_pii_kind("full_name") == "full_name"

    def test_unknown_returns_none(self):
        assert detect_pii_kind("sku") is None
        assert detect_pii_kind("qty") is None
        assert detect_pii_kind("id") is None


# ── Synthesizer ────────────────────────────────────────────────────────

class TestSynthesize:
    def setup_method(self):
        self.rng = random.Random(0)

    def test_email_is_example_com(self):
        assert synthesize("email", 1, self.rng) == "user1@example.com"

    def test_ssn_always_dummy(self):
        val = synthesize("ssn", 42, self.rng)
        assert val.startswith("000-00-")

    def test_credit_card_always_test(self):
        val = synthesize("credit_card", 1, self.rng)
        assert val.startswith("4111-")

    def test_password_is_opaque(self):
        val = synthesize("password", 1, self.rng)
        assert val == "hashed-dummy-password"

    def test_ip_is_test_net(self):
        val = synthesize("ip", 10, self.rng)
        assert val.startswith("203.0.113.")  # TEST-NET-3

    def test_integer_column_type_returns_int(self):
        assert synthesize_for_type("integer", "id", 5, self.rng) == 5

    def test_text_column_type_uses_name(self):
        val = synthesize_for_type("text", "sku", 3, self.rng)
        assert val == "sku-3"

    def test_boolean_column(self):
        assert synthesize_for_type("boolean", "active", 2, self.rng) is True
        assert synthesize_for_type("boolean", "active", 3, self.rng) is False


# ── Parser ─────────────────────────────────────────────────────────────

class TestParsePsqlDescribe:
    def test_parses_standard_output(self):
        raw = """
 column_name | data_type | is_nullable
-------------+-----------+-------------
 id          | integer   | NO
 email       | text      | NO
 name        | text      | YES
(3 rows)
"""
        spec = parse_psql_describe(raw, "users")
        assert spec.name == "users"
        assert len(spec.columns) == 3
        assert spec.columns[0].name == "id"
        assert spec.columns[0].sql_type == "integer"
        assert spec.columns[0].nullable is False
        assert spec.columns[1].pii_kind == "email"

    def test_tolerates_extra_whitespace_and_separators(self):
        raw = "sku  |  text\nqty |  integer"
        spec = parse_psql_describe(raw, "items")
        assert [c.name for c in spec.columns] == ["sku", "qty"]

    def test_empty_output_yields_empty_spec(self):
        spec = parse_psql_describe("", "empty")
        assert spec.columns == []


# ── Insert rendering ───────────────────────────────────────────────────

class TestRenderInserts:
    def test_generates_row_count_statements(self):
        spec = TableSpec(
            name="users",
            columns=[
                ColumnSpec(name="id", sql_type="integer").classify(),
                ColumnSpec(name="email", sql_type="text").classify(),
            ],
        )
        stmts = render_inserts(spec, 3)
        assert len(stmts) == 3
        for s in stmts:
            assert s.startswith("INSERT INTO users")
            assert "@example.com" in s

    def test_pii_columns_get_synthetic_values(self):
        spec = TableSpec(
            name="people",
            columns=[
                ColumnSpec(name="ssn", sql_type="text").classify(),
            ],
        )
        stmts = render_inserts(spec, 1)
        assert "'000-00-" in stmts[0]

    def test_non_pii_columns_use_type(self):
        spec = TableSpec(
            name="orders",
            columns=[
                ColumnSpec(name="id", sql_type="integer").classify(),
                ColumnSpec(name="sku", sql_type="text").classify(),
            ],
        )
        stmts = render_inserts(spec, 2)
        assert "(1, 'sku-1')" in stmts[0]
        assert "(2, 'sku-2')" in stmts[1]

    def test_determinism_with_seed(self):
        spec = TableSpec(
            name="people",
            columns=[
                ColumnSpec(name="first_name", sql_type="text").classify(),
            ],
        )
        a = render_inserts(spec, 5, seed=42)
        b = render_inserts(spec, 5, seed=42)
        assert a == b

    def test_sql_quoting_escapes_quotes(self):
        # This path is hit if a synthesizer ever produces a value with `'`
        # in it. Our synthesizers don't today, but the hygiene matters.
        from pysandbox.engine.fork_production import _sql_literal
        assert _sql_literal("O'Hara") == "'O''Hara'"


# ── Engine ─────────────────────────────────────────────────────────────

class TestEngine:
    @pytest.fixture
    def tool_registry(self):
        registry = MagicMock()
        self.sql_query_result = (
            " column_name | data_type | is_nullable\n"
            "-------------+-----------+-------------\n"
            " id | integer | NO\n"
            " email | text | NO\n"
        )

        def get_tool(sid, name):
            tool = MagicMock()
            if name == "sql_query":
                tool.handler = AsyncMock(return_value=self.sql_query_result)
            elif name == "sql_execute":
                tool.handler = AsyncMock(return_value="INSERT 0 1")
            else:
                return None
            return tool

        registry.get_tool = MagicMock(side_effect=get_tool)
        return registry

    @pytest.mark.asyncio
    async def test_introspect_returns_populated_tables(self, tool_registry):
        engine = ForkFromProductionEngine(tool_registry)
        specs = await engine.introspect("sb-src", ["users"])
        assert len(specs) == 1
        assert specs[0].name == "users"
        assert [c.name for c in specs[0].columns] == ["id", "email"]

    @pytest.mark.asyncio
    async def test_introspect_raises_when_no_sql_tool(self):
        registry = MagicMock()
        registry.get_tool = MagicMock(return_value=None)
        engine = ForkFromProductionEngine(registry)
        with pytest.raises(ValueError, match="sql_query"):
            await engine.introspect("sb-src", ["users"])

    @pytest.mark.asyncio
    async def test_apply_runs_every_insert(self, tool_registry):
        engine = ForkFromProductionEngine(tool_registry)
        specs = await engine.introspect("sb-src", ["users"])
        plan = engine.plan(specs, rows_per_table=3)
        result = await engine.apply("sb-dst", plan)
        assert result["total_inserted"] == 3
        assert result["per_table"][0]["table"] == "users"

    @pytest.mark.asyncio
    async def test_apply_collects_errors(self, tool_registry):
        engine = ForkFromProductionEngine(tool_registry)
        specs = await engine.introspect("sb-src", ["users"])
        plan = engine.plan(specs, rows_per_table=2)
        # First call fails, second call succeeds.
        calls = {"n": 0}

        async def maybe_fail(args):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("conflict")
            return "INSERT 0 1"

        tool_registry.get_tool = MagicMock(return_value=MagicMock(
            handler=maybe_fail,
        ))
        result = await engine.apply("sb-dst", plan)
        # We still report totals honestly.
        assert result["per_table"][0]["errors"]
        assert result["total_inserted"] == 1
