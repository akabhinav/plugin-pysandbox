"""Sandbox Data Seeder — pre-loads realistic sample data into plugins.

After seeding, developers have actual data to work with instead of empty databases.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pysandbox.agent.tool_registry import AgentToolRegistry
    from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo

logger = structlog.get_logger()


@dataclass
class SeedStepResult:
    name: str
    plugin: str
    success: bool
    message: str
    rows_created: int = 0


@dataclass
class SeedResult:
    sandbox_id: str
    total_steps: int = 0
    succeeded: int = 0
    failed: int = 0
    steps: list[SeedStepResult] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "success": self.failed == 0 and self.total_steps > 0,
            "total_steps": self.total_steps,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "duration_ms": self.duration_ms,
            "steps": [
                {
                    "name": s.name,
                    "plugin": s.plugin,
                    "success": s.success,
                    "message": s.message,
                    "rows_created": s.rows_created,
                }
                for s in self.steps
            ],
        }


# ── Seed definitions per plugin ──────────────────────────────────────────────

SEED_DEFINITIONS: dict[str, list[dict[str, Any]]] = {
    "postgres": [
        {
            "name": "Create users table",
            "tool": "sql_execute",
            "params": {"statement": """
                CREATE TABLE IF NOT EXISTS users (
                    id serial PRIMARY KEY,
                    name text NOT NULL,
                    email text UNIQUE NOT NULL,
                    role text DEFAULT 'user',
                    created_at timestamp DEFAULT now()
                )
            """},
            "rows": 0,
        },
        {
            "name": "Insert sample users",
            "tool": "sql_execute",
            "params": {"statement": """
                INSERT INTO users (name, email, role) VALUES
                ('Alice Johnson', 'alice@example.com', 'admin'),
                ('Bob Smith', 'bob@example.com', 'user'),
                ('Charlie Brown', 'charlie@example.com', 'user'),
                ('Diana Prince', 'diana@example.com', 'moderator'),
                ('Eve Wilson', 'eve@example.com', 'user')
                ON CONFLICT (email) DO NOTHING
            """},
            "rows": 5,
        },
        {
            "name": "Create orders table",
            "tool": "sql_execute",
            "params": {"statement": """
                CREATE TABLE IF NOT EXISTS orders (
                    id serial PRIMARY KEY,
                    user_id int REFERENCES users(id),
                    product text NOT NULL,
                    amount decimal(10,2) NOT NULL,
                    status text DEFAULT 'pending',
                    created_at timestamp DEFAULT now()
                )
            """},
            "rows": 0,
        },
        {
            "name": "Insert sample orders",
            "tool": "sql_execute",
            "params": {"statement": """
                INSERT INTO orders (user_id, product, amount, status) VALUES
                (1, 'Laptop Pro', 1299.99, 'completed'),
                (1, 'Wireless Mouse', 49.99, 'completed'),
                (2, 'Mechanical Keyboard', 159.99, 'shipped'),
                (3, 'Monitor 27"', 399.99, 'pending'),
                (4, 'USB-C Hub', 79.99, 'completed'),
                (2, 'Webcam HD', 89.99, 'pending'),
                (5, 'Headset Pro', 199.99, 'shipped'),
                (3, 'SSD 1TB', 119.99, 'completed')
                ON CONFLICT DO NOTHING
            """},
            "rows": 8,
        },
        {
            "name": "Create analytics view",
            "tool": "sql_execute",
            "params": {"statement": """
                CREATE OR REPLACE VIEW order_summary AS
                SELECT u.name, u.email, count(o.id) as order_count,
                       coalesce(sum(o.amount), 0) as total_spent
                FROM users u LEFT JOIN orders o ON u.id = o.user_id
                GROUP BY u.id, u.name, u.email
            """},
            "rows": 0,
        },
    ],
    "mysql": [
        {
            "name": "Create users table",
            "tool": "sql_execute",
            "params": {"statement": "CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), email VARCHAR(100) UNIQUE, role VARCHAR(50) DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"},
            "rows": 0,
        },
        {
            "name": "Insert sample users",
            "tool": "sql_execute",
            "params": {"statement": "INSERT IGNORE INTO users (name, email, role) VALUES ('Alice Johnson', 'alice@example.com', 'admin'), ('Bob Smith', 'bob@example.com', 'user'), ('Charlie Brown', 'charlie@example.com', 'user')"},
            "rows": 3,
        },
    ],
    "redis": [
        {
            "name": "Set app config",
            "tool": "redis_set",
            "params": {"key": "app:config:theme", "value": "dark"},
            "rows": 1,
        },
        {
            "name": "Set feature flags",
            "tool": "redis_set",
            "params": {"key": "feature:new_dashboard", "value": "enabled"},
            "rows": 1,
        },
        {
            "name": "Set rate limit counter",
            "tool": "redis_set",
            "params": {"key": "ratelimit:api:global", "value": "0"},
            "rows": 1,
        },
        {
            "name": "Set session data",
            "tool": "redis_set",
            "params": {"key": "session:user:alice", "value": "{\"user_id\": 1, \"role\": \"admin\", \"login_at\": \"2024-01-15T10:00:00Z\"}"},
            "rows": 1,
        },
        {
            "name": "Set cache sample",
            "tool": "redis_set",
            "params": {"key": "cache:homepage:stats", "value": "{\"users\": 5, \"orders\": 8, \"revenue\": 2399.92}"},
            "rows": 1,
        },
    ],
    "kafka": [
        {
            "name": "Create user-events topic",
            "tool": "kafka_create_topic",
            "params": {"topic": "user-events", "partitions": 3, "replication_factor": 1},
            "rows": 0,
        },
        {
            "name": "Create order-events topic",
            "tool": "kafka_create_topic",
            "params": {"topic": "order-events", "partitions": 3, "replication_factor": 1},
            "rows": 0,
        },
        {
            "name": "Create notifications topic",
            "tool": "kafka_create_topic",
            "params": {"topic": "notifications", "partitions": 1, "replication_factor": 1},
            "rows": 0,
        },
        {
            "name": "Publish sample user event",
            "tool": "kafka_produce",
            "params": {"topic": "user-events", "message": "{\"type\": \"user.created\", \"user_id\": 1, \"name\": \"Alice\"}"},
            "rows": 1,
        },
        {
            "name": "Publish sample order event",
            "tool": "kafka_produce",
            "params": {"topic": "order-events", "message": "{\"type\": \"order.placed\", \"order_id\": 101, \"amount\": 1299.99}"},
            "rows": 1,
        },
    ],
    "mongodb": [
        {
            "name": "Insert sample products",
            "tool": "mongo_insert",
            "params": {"collection": "products", "document": {"name": "Laptop Pro", "price": 1299.99, "category": "electronics", "in_stock": True, "tags": ["laptop", "premium"]}},
            "rows": 1,
        },
        {
            "name": "Insert sample product 2",
            "tool": "mongo_insert",
            "params": {"collection": "products", "document": {"name": "Wireless Mouse", "price": 49.99, "category": "accessories", "in_stock": True, "tags": ["mouse", "wireless"]}},
            "rows": 1,
        },
        {
            "name": "Insert sample log entry",
            "tool": "mongo_insert",
            "params": {"collection": "logs", "document": {"level": "info", "message": "Application started", "service": "api", "timestamp": "2024-01-15T10:00:00Z"}},
            "rows": 1,
        },
    ],
    "neo4j": [
        {
            "name": "Create person nodes",
            "tool": "cypher_query",
            "params": {"query": "MERGE (a:Person {name: 'Alice', role: 'Engineer'}) MERGE (b:Person {name: 'Bob', role: 'Manager'}) MERGE (c:Person {name: 'Charlie', role: 'Designer'}) RETURN count(*) AS created"},
            "rows": 3,
        },
        {
            "name": "Create relationships",
            "tool": "cypher_query",
            "params": {"query": "MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'}) MERGE (a)-[:REPORTS_TO]->(b) WITH a, b MATCH (c:Person {name: 'Charlie'}) MERGE (c)-[:REPORTS_TO]->(b) MERGE (a)-[:COLLABORATES_WITH]->(c) RETURN count(*) AS relationships"},
            "rows": 3,
        },
    ],
    "clickhouse": [
        {
            "name": "Create events table",
            "tool": "clickhouse_query",
            "params": {"query": "CREATE TABLE IF NOT EXISTS events (event_time DateTime DEFAULT now(), event_type String, user_id UInt32, properties String) ENGINE = MergeTree() ORDER BY event_time"},
            "rows": 0,
        },
        {
            "name": "Insert sample events",
            "tool": "clickhouse_query",
            "params": {"query": "INSERT INTO events (event_type, user_id, properties) VALUES ('page_view', 1, '{\"page\": \"/home\"}'), ('click', 2, '{\"button\": \"signup\"}'), ('page_view', 1, '{\"page\": \"/dashboard\"}'), ('purchase', 3, '{\"amount\": 99.99}')"},
            "rows": 4,
        },
    ],
}


class SandboxSeeder:
    """Pre-loads sample data into sandbox plugins via their agent tools."""

    def __init__(
        self,
        tool_registry: "AgentToolRegistry",
        instance_repo: "PluginInstanceRepo",
    ) -> None:
        self._tools = tool_registry
        self._repo = instance_repo

    async def seed(self, sandbox_id: str) -> SeedResult:
        """Seed all installed plugins with sample data."""
        start = time.monotonic()
        result = SeedResult(sandbox_id=sandbox_id)
        log = logger.bind(sandbox_id=sandbox_id)
        log.info("seed_start")

        instances = await self._repo.list_instances(sandbox_id)
        installed = {
            inst["plugin_name"]: inst["plugin_id"]
            for inst in instances
        }

        for plugin_name, plugin_id in installed.items():
            seed_steps = SEED_DEFINITIONS.get(plugin_id, [])
            if not seed_steps:
                continue

            for step in seed_steps:
                result.total_steps += 1
                step_result = await self._run_seed_step(
                    sandbox_id, plugin_name, step
                )
                result.steps.append(step_result)
                if step_result.success:
                    result.succeeded += 1
                else:
                    result.failed += 1
                    # Stop seeding this plugin on failure
                    break

        result.duration_ms = int((time.monotonic() - start) * 1000)
        log.info("seed_complete", succeeded=result.succeeded, failed=result.failed, ms=result.duration_ms)
        return result

    async def _run_seed_step(
        self, sandbox_id: str, plugin_name: str, step: dict[str, Any]
    ) -> SeedStepResult:
        tool_name = step["tool"]
        params = step.get("params", {})

        tool = self._tools.get_tool(sandbox_id, tool_name)
        if not tool:
            return SeedStepResult(
                name=step["name"],
                plugin=plugin_name,
                success=False,
                message=f"Tool '{tool_name}' not registered",
            )

        try:
            output = await asyncio.wait_for(tool.handler(params), timeout=30)
            output_str = str(output).lower() if output else ""
            # Check for obvious errors
            if "error" in output_str and "0 error" not in output_str:
                return SeedStepResult(
                    name=step["name"],
                    plugin=plugin_name,
                    success=False,
                    message=f"Error: {output_str[:200]}",
                )
            return SeedStepResult(
                name=step["name"],
                plugin=plugin_name,
                success=True,
                message="OK",
                rows_created=step.get("rows", 0),
            )
        except asyncio.TimeoutError:
            return SeedStepResult(
                name=step["name"],
                plugin=plugin_name,
                success=False,
                message="Timed out after 30s",
            )
        except Exception as e:
            return SeedStepResult(
                name=step["name"],
                plugin=plugin_name,
                success=False,
                message=str(e),
            )
