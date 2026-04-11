"""Fork-from-production — clone a production schema into a dev sandbox
and populate it with PII-safe synthetic data.

The goal is to reproduce prod-shaped bugs in dev *without* copying real
user data. The flow is:

1. **Schema introspection** — run information_schema queries against
   the source database to discover tables, columns, and foreign keys.
   This step uses the existing `sql_query` agent tool so it works
   against any sandbox that already has postgres (or a target with
   the same SQL dialect).

2. **PII detection** — tag columns that look like PII based on their
   name. This uses a simple keyword matcher; any column whose name
   contains `email`, `phone`, `ssn`, etc. is flagged and will be
   generated synthetically rather than copied.

3. **Synthetic data generation** — emit a set of INSERT statements
   for each table using a seeded random generator so runs are
   reproducible. The generator is column-type-aware: integers get
   sequential ints, `email` columns get `user{n}@example.com`, etc.

4. **Apply** — run the INSERTs through `sql_execute` on a target
   sandbox (typically a fresh one created for this fork).

Nothing in this module reaches out to a real production database
by itself — it always goes through the agent tool layer, so any
credentials stay inside the sandbox boundary and the same code works
for postgres/mysql/any future SQL plugin.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


# ── PII detection ──────────────────────────────────────────────────────

# Column-name substring → synthetic-value generator category.
# Order matters: longer / more specific keywords go first so "email_verified"
# matches `email` before generic string handling.
_PII_KEYWORDS: list[tuple[str, str]] = [
    ("email", "email"),
    ("e_mail", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("telephone", "phone"),
    ("ssn", "ssn"),
    ("social_security", "ssn"),
    ("credit_card", "credit_card"),
    ("card_number", "credit_card"),
    ("password", "password"),
    ("passwd", "password"),
    ("secret", "secret"),
    ("token", "token"),
    ("api_key", "token"),
    ("first_name", "first_name"),
    ("last_name", "last_name"),
    ("full_name", "full_name"),
    ("street", "street"),
    ("address", "address"),
    ("dob", "date"),
    ("birthdate", "date"),
    ("birthday", "date"),
    ("ip_address", "ip"),
]


def detect_pii_kind(column_name: str) -> str | None:
    """Return a synthetic generator kind for a column name, or None if
    the column is not obviously PII."""
    lc = column_name.lower()
    for keyword, kind in _PII_KEYWORDS:
        if keyword in lc:
            return kind
    return None


# ── Synthetic value generator ──────────────────────────────────────────

_FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry",
    "Iris", "Jack", "Kate", "Liam", "Mia", "Noah", "Olivia", "Peter",
]
_LAST_NAMES = [
    "Adams", "Brown", "Carter", "Davis", "Evans", "Ford", "Green", "Hill",
    "Jones", "King", "Lee", "Moore", "Nelson", "Owen", "Parker", "Quinn",
]
_STREETS = [
    "Main St", "Oak Ave", "Pine Rd", "Maple Dr", "Cedar Ln", "Elm Ct",
]


def synthesize(kind: str, row_index: int, rng: random.Random) -> Any:
    """Return a synthetic value for the given PII kind.

    `row_index` is used as a deterministic seed so that, given the same
    rng state, we produce the same output — helpful for reproducible
    tests. All values are obviously-fake (no "realistic" email addresses
    on real domains) so they can't be confused with real data in logs.
    """
    if kind == "email":
        return f"user{row_index}@example.com"
    if kind == "phone":
        return f"555-{row_index:04d}"
    if kind == "ssn":
        # Always a dummy SSN (000-00-XXXX is never assigned by the SSA).
        return f"000-00-{row_index % 10000:04d}"
    if kind == "credit_card":
        # Always a test-card Luhn-safe prefix.
        return f"4111-1111-1111-{row_index % 10000:04d}"
    if kind == "password":
        return "hashed-dummy-password"
    if kind in ("secret", "token"):
        return f"dummy-{kind}-{row_index}"
    if kind == "first_name":
        return rng.choice(_FIRST_NAMES)
    if kind == "last_name":
        return rng.choice(_LAST_NAMES)
    if kind == "full_name":
        return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
    if kind == "street":
        return f"{row_index} {rng.choice(_STREETS)}"
    if kind == "address":
        return f"{row_index} {rng.choice(_STREETS)}, Springfield"
    if kind == "date":
        y = 1970 + (row_index % 50)
        m = (row_index % 12) + 1
        d = (row_index % 28) + 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    if kind == "ip":
        return f"203.0.113.{row_index % 256}"  # TEST-NET-3, never real
    return f"synthetic-{row_index}"


def synthesize_for_type(
    sql_type: str, column_name: str, row_index: int, rng: random.Random,
) -> Any:
    """Pick a synthetic value based on column type + name.

    Called when no PII match was found. This handles the common types
    pysandbox users see: integer, bigint, text, varchar, boolean,
    numeric, timestamp. Unknown types fall back to NULL so the caller
    at least gets a syntactically valid insert.
    """
    t = sql_type.lower()
    if "int" in t or "serial" in t:
        return row_index
    if "bool" in t:
        return row_index % 2 == 0
    if "numeric" in t or "decimal" in t or "double" in t or "real" in t or "float" in t:
        return round(rng.uniform(1.0, 1000.0), 2)
    if "timestamp" in t or "date" in t:
        y = 2020 + (row_index % 6)
        m = (row_index % 12) + 1
        d = (row_index % 28) + 1
        return f"{y:04d}-{m:02d}-{d:02d} 12:00:00"
    if "char" in t or "text" in t or "string" in t:
        # Use the column name as a hint so tests can assert "sku" gets
        # sku-shaped strings, "status" gets a status-shaped string, etc.
        return f"{column_name}-{row_index}"
    return None


# ── Schema & plan ──────────────────────────────────────────────────────

@dataclass
class ColumnSpec:
    name: str
    sql_type: str
    nullable: bool = True
    pii_kind: str | None = None

    def classify(self) -> "ColumnSpec":
        if self.pii_kind is None:
            self.pii_kind = detect_pii_kind(self.name)
        return self


@dataclass
class TableSpec:
    name: str
    columns: list[ColumnSpec] = field(default_factory=list)

    @property
    def pii_columns(self) -> list[ColumnSpec]:
        return [c for c in self.columns if c.pii_kind is not None]


@dataclass
class ForkPlan:
    """What we intend to generate for each table in the fork."""

    tables: list[TableSpec]
    rows_per_table: int = 50
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "rows_per_table": self.rows_per_table,
            "tables": [
                {
                    "name": t.name,
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.sql_type,
                            "nullable": c.nullable,
                            "pii_kind": c.pii_kind,
                        }
                        for c in t.columns
                    ],
                    "pii_columns": [c.name for c in t.pii_columns],
                }
                for t in self.tables
            ],
        }


# ── Plan parser (from raw SQL output) ──────────────────────────────────

# Minimal parser for the `\d+` / information_schema output we'll typically
# get from the sql_query tool. We keep this tolerant: if a row doesn't
# match, it's silently skipped — the worst case is that we generate
# fewer synthetic rows than the real schema has columns, never crash.

_COLUMN_LINE = re.compile(
    r"^\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*\|\s*(?P<type>[a-zA-Z_][a-zA-Z0-9_ ()]*?)\s*(\|\s*(?P<nullable>YES|NO))?\s*$",
    re.IGNORECASE,
)


def parse_psql_describe(output: str, table_name: str) -> TableSpec:
    r"""Parse SELECT column_name, data_type, is_nullable FROM information_schema.columns.

    Very forgiving: we only accept lines that have at least `name | type`
    separated by pipes; everything else is skipped. This tolerates both
    psql's pretty `\d+` output and raw information_schema dumps.
    """
    cols: list[ColumnSpec] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or set(line) <= {"-", "+"}:
            continue
        m = _COLUMN_LINE.match(line)
        if not m:
            continue
        col_name = m.group("name")
        col_type = m.group("type").strip()
        # Skip psql's header row specifically. We only treat a line as
        # a header when the *type* column contains the literal
        # "data_type" — that way a real column called "name" with type
        # "text" still gets captured.
        if col_type.lower() in ("data_type", "type"):
            continue
        cols.append(ColumnSpec(
            name=col_name,
            sql_type=col_type,
            nullable=(m.group("nullable") or "YES").upper() == "YES",
        ).classify())
    return TableSpec(name=table_name, columns=cols)


# ── Insert statement rendering ─────────────────────────────────────────

def _sql_literal(value: Any) -> str:
    """Quote a value as a SQL literal. Only safe for synthetic data —
    never use this for untrusted input."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def render_inserts(table: TableSpec, row_count: int, seed: int = 42) -> list[str]:
    """Render `row_count` INSERT statements for a table, one per row.

    We deliberately emit one INSERT per row rather than a batched
    multi-VALUES insert, because:
      - it's easier to pass through sql_execute, which truncates long
        statements in some plugins
      - it makes partial failures observable in the apply phase
    """
    if not table.columns:
        return []
    rng = random.Random(seed + hash(table.name))
    statements = []
    col_names = ", ".join(c.name for c in table.columns)
    for i in range(row_count):
        values = []
        for c in table.columns:
            if c.pii_kind is not None:
                values.append(synthesize(c.pii_kind, i + 1, rng))
            else:
                values.append(synthesize_for_type(c.sql_type, c.name, i + 1, rng))
        rendered = ", ".join(_sql_literal(v) for v in values)
        statements.append(f"INSERT INTO {table.name} ({col_names}) VALUES ({rendered});")
    return statements


# ── High-level engine ──────────────────────────────────────────────────

class ForkFromProductionEngine:
    """Glue layer: introspect source, plan, optionally apply to target.

    The engine takes a `tool_registry` so it can invoke agent tools on
    both the source sandbox (for introspection) and the target sandbox
    (for applying synthesized INSERTs). The two can be the same sandbox
    for "rewrite this schema with synthetic data" workflows.
    """

    def __init__(self, tool_registry) -> None:
        self._registry = tool_registry

    async def introspect(
        self, source_sandbox_id: str, tables: list[str],
    ) -> list[TableSpec]:
        """Query information_schema on the source for each table."""
        tool = self._registry.get_tool(source_sandbox_id, "sql_query")
        if tool is None:
            raise ValueError(
                f"source sandbox {source_sandbox_id} has no sql_query tool "
                "— is a postgres/mysql plugin installed?",
            )
        specs: list[TableSpec] = []
        for name in tables:
            query = (
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                f"WHERE table_name = '{name}' "
                "ORDER BY ordinal_position"
            )
            raw = await tool.handler({"query": query})
            output = raw if isinstance(raw, str) else str(raw)
            specs.append(parse_psql_describe(output, name))
        return specs

    def plan(
        self,
        tables: list[TableSpec],
        *,
        rows_per_table: int = 50,
        seed: int = 42,
    ) -> ForkPlan:
        return ForkPlan(tables=tables, rows_per_table=rows_per_table, seed=seed)

    def render_statements(self, plan: ForkPlan) -> list[tuple[str, list[str]]]:
        """Return a (table_name, [insert statements]) pair for each table."""
        result = []
        for t in plan.tables:
            result.append((t.name, render_inserts(t, plan.rows_per_table, plan.seed)))
        return result

    async def apply(
        self, target_sandbox_id: str, plan: ForkPlan,
    ) -> dict[str, Any]:
        """Run every INSERT from the plan against the target sandbox."""
        tool = self._registry.get_tool(target_sandbox_id, "sql_execute")
        if tool is None:
            raise ValueError(
                f"target sandbox {target_sandbox_id} has no sql_execute tool",
            )
        results = []
        total_inserted = 0
        for table_name, statements in self.render_statements(plan):
            inserted = 0
            errors = []
            for stmt in statements:
                try:
                    await tool.handler({"statement": stmt})
                    inserted += 1
                except Exception as e:
                    errors.append(str(e)[:120])
            total_inserted += inserted
            results.append({
                "table": table_name,
                "inserted": inserted,
                "errors": errors[:3],  # cap noise
            })
        return {
            "target_sandbox_id": target_sandbox_id,
            "total_inserted": total_inserted,
            "per_table": results,
        }
