"""Sandbox Verification Engine — smoke-test plugins and cross-plugin connectivity.

Runs real workloads through agent tools to verify a sandbox actually works,
not just that containers report healthy.
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
    from pysandbox.runtime.docker_runtime import DockerRuntime

logger = structlog.get_logger()


@dataclass
class VerifyStepResult:
    """Result of a single verification step."""

    name: str
    plugin: str
    passed: bool
    message: str
    duration_ms: int = 0
    output: str = ""
    category: str = "plugin"  # "plugin" or "cross-plugin"


@dataclass
class VerifyResult:
    """Full verification result for a sandbox."""

    sandbox_id: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    steps: list[VerifyStepResult] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "success": self.success,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
            "steps": [
                {
                    "name": s.name,
                    "plugin": s.plugin,
                    "passed": s.passed,
                    "message": s.message,
                    "duration_ms": s.duration_ms,
                    "output": s.output[:500],  # Truncate large output
                    "category": s.category,
                }
                for s in self.steps
            ],
        }


# ── Per-plugin verification definitions ──────────────────────────────────────
# Each plugin_id maps to a list of (step_name, tool_name, params, validator)
# validator is a callable: (output: str) -> (passed: bool, message: str)

def _not_empty(output: str) -> tuple[bool, str]:
    if output and output.strip():
        return True, "Got response"
    return False, "Empty response"


def _contains(expected: str):
    def check(output: str) -> tuple[bool, str]:
        if expected.lower() in output.lower():
            return True, f"Contains '{expected}'"
        return False, f"Expected '{expected}' not found in output"
    return check


def _no_error(output: str) -> tuple[bool, str]:
    error_markers = ["error", "exception", "fatal", "refused", "denied"]
    lower = output.lower()
    for marker in error_markers:
        if marker in lower and "0 error" not in lower:
            return False, f"Error detected: {output[:200]}"
    return True, "No errors"


PLUGIN_CHECKS: dict[str, list[dict[str, Any]]] = {
    "postgres": [
        {
            "name": "SQL SELECT",
            "tool": "sql_query",
            "params": {"query": "SELECT 1 AS health_check"},
            "validate": _contains("1"),
        },
        {
            "name": "Create test table",
            "tool": "sql_execute",
            "params": {"statement": "CREATE TABLE IF NOT EXISTS _verify_test (id serial PRIMARY KEY, name text, created_at timestamp DEFAULT now()); INSERT INTO _verify_test (name) VALUES ('verify_ok');"},
            "validate": _no_error,
        },
        {
            "name": "Read test table",
            "tool": "sql_query",
            "params": {"query": "SELECT name FROM _verify_test WHERE name = 'verify_ok'"},
            "validate": _contains("verify_ok"),
        },
        {
            "name": "Cleanup test table",
            "tool": "sql_execute",
            "params": {"statement": "DROP TABLE IF EXISTS _verify_test"},
            "validate": _no_error,
        },
    ],
    "mysql": [
        {
            "name": "SQL SELECT",
            "tool": "sql_query",
            "params": {"query": "SELECT 1 AS health_check"},
            "validate": _contains("1"),
        },
        {
            "name": "List tables",
            "tool": "list_tables",
            "params": {},
            "validate": _no_error,
        },
    ],
    "redis": [
        {
            "name": "SET key",
            "tool": "redis_set",
            "params": {"key": "_verify_test", "value": "verify_ok"},
            "validate": _no_error,
        },
        {
            "name": "GET key",
            "tool": "redis_get",
            "params": {"key": "_verify_test"},
            "validate": _contains("verify_ok"),
        },
        {
            "name": "List keys",
            "tool": "redis_scan",
            "params": {"pattern": "_verify*"},
            "validate": _contains("_verify_test"),
        },
    ],
    "kafka": [
        {
            "name": "Create topic",
            "tool": "kafka_create_topic",
            "params": {"topic": "_verify_test", "partitions": 1, "replication_factor": 1},
            "validate": _no_error,
        },
        {
            "name": "List topics",
            "tool": "kafka_list_topics",
            "params": {},
            "validate": _contains("_verify_test"),
        },
        {
            "name": "Produce message",
            "tool": "kafka_produce",
            "params": {"topic": "_verify_test", "message": "verify_ok"},
            "validate": _no_error,
        },
        {
            "name": "Delete topic",
            "tool": "kafka_delete_topic",
            "params": {"topic": "_verify_test"},
            "validate": _no_error,
        },
    ],
    "mongodb": [
        {
            "name": "Insert document",
            "tool": "mongo_insert",
            "params": {"collection": "_verify_test", "document": {"check": "verify_ok"}},
            "validate": _no_error,
        },
        {
            "name": "Find document",
            "tool": "mongo_find",
            "params": {"collection": "_verify_test", "filter": {"check": "verify_ok"}},
            "validate": _contains("verify_ok"),
        },
    ],
    "elasticsearch": [
        {
            "name": "Cluster health",
            "tool": "es_cluster_health",
            "params": {},
            "validate": _not_empty,
        },
    ],
    "minio": [
        {
            "name": "List buckets",
            "tool": "s3_list_buckets",
            "params": {},
            "validate": _no_error,
        },
    ],
    "neo4j": [
        {
            "name": "Cypher query",
            "tool": "cypher_query",
            "params": {"query": "RETURN 1 AS health"},
            "validate": _not_empty,
        },
    ],
    "clickhouse": [
        {
            "name": "SQL SELECT",
            "tool": "clickhouse_query",
            "params": {"query": "SELECT 1"},
            "validate": _contains("1"),
        },
    ],
}


# ── Cross-plugin verification workflows ──────────────────────────────────────
# Keyed by template_id, each is a list of steps that test plugin-to-plugin comms

CROSS_PLUGIN_CHECKS: dict[str, list[dict[str, Any]]] = {
    "microservices": [
        {
            "name": "Postgres → write event data",
            "plugin": "postgres",
            "tool": "sql_execute",
            "params": {"statement": "CREATE TABLE IF NOT EXISTS events (id serial, source text, payload text); INSERT INTO events (source, payload) VALUES ('kafka', 'cross_plugin_verify');"},
            "validate": _no_error,
        },
        {
            "name": "Redis → cache event lookup",
            "plugin": "redis",
            "tool": "redis_set",
            "params": {"key": "event:latest", "value": "cross_plugin_verify"},
            "validate": _no_error,
        },
        {
            "name": "Kafka → publish event notification",
            "plugin": "kafka",
            "tool": "kafka_produce",
            "params": {"topic": "events", "message": "cross_plugin_verify"},
            "validate": _no_error,
        },
        {
            "name": "Redis → verify cached event",
            "plugin": "redis",
            "tool": "redis_get",
            "params": {"key": "event:latest"},
            "validate": _contains("cross_plugin_verify"),
        },
        {
            "name": "Postgres → verify stored event",
            "plugin": "postgres",
            "tool": "sql_query",
            "params": {"query": "SELECT payload FROM events WHERE payload = 'cross_plugin_verify'"},
            "validate": _contains("cross_plugin_verify"),
        },
        {
            "name": "Cleanup",
            "plugin": "postgres",
            "tool": "sql_execute",
            "params": {"statement": "DROP TABLE IF EXISTS events"},
            "validate": _no_error,
        },
    ],
    "event-driven": [
        {
            "name": "Kafka → create events topic",
            "plugin": "kafka",
            "tool": "kafka_create_topic",
            "params": {"topic": "cross_verify", "partitions": 1, "replication_factor": 1},
            "validate": _no_error,
        },
        {
            "name": "Kafka → produce event",
            "plugin": "kafka",
            "tool": "kafka_produce",
            "params": {"topic": "cross_verify", "message": "event_driven_verify"},
            "validate": _no_error,
        },
        {
            "name": "Redis → store event state",
            "plugin": "redis",
            "tool": "redis_set",
            "params": {"key": "processed:cross_verify", "value": "true"},
            "validate": _no_error,
        },
        {
            "name": "Redis → confirm event state",
            "plugin": "redis",
            "tool": "redis_get",
            "params": {"key": "processed:cross_verify"},
            "validate": _contains("true"),
        },
        {
            "name": "Cleanup",
            "plugin": "kafka",
            "tool": "kafka_delete_topic",
            "params": {"topic": "cross_verify"},
            "validate": _no_error,
        },
    ],
    "ml-pipeline": [
        {
            "name": "Postgres → create dataset table",
            "plugin": "postgres",
            "tool": "sql_execute",
            "params": {"statement": "CREATE TABLE IF NOT EXISTS ml_features (id serial, feature_1 float, feature_2 float, label int); INSERT INTO ml_features (feature_1, feature_2, label) VALUES (1.0, 2.0, 1), (3.0, 4.0, 0);"},
            "validate": _no_error,
        },
        {
            "name": "Postgres → query dataset",
            "plugin": "postgres",
            "tool": "sql_query",
            "params": {"query": "SELECT count(*) FROM ml_features"},
            "validate": _contains("2"),
        },
        {
            "name": "MinIO → verify storage ready",
            "plugin": "minio",
            "tool": "s3_list_buckets",
            "params": {},
            "validate": _no_error,
        },
        {
            "name": "Cleanup",
            "plugin": "postgres",
            "tool": "sql_execute",
            "params": {"statement": "DROP TABLE IF EXISTS ml_features"},
            "validate": _no_error,
        },
    ],
    "data-lakehouse": [
        {
            "name": "MinIO → verify object storage",
            "plugin": "minio",
            "tool": "s3_list_buckets",
            "params": {},
            "validate": _no_error,
        },
        {
            "name": "Nessie → list branches",
            "plugin": "nessie",
            "tool": "nessie_list_branches",
            "params": {},
            "validate": _not_empty,
        },
    ],
    "search-analytics": [
        {
            "name": "Elasticsearch → cluster health",
            "plugin": "elasticsearch",
            "tool": "es_cluster_health",
            "params": {},
            "validate": _not_empty,
        },
        {
            "name": "ClickHouse → test query",
            "plugin": "clickhouse",
            "tool": "clickhouse_query",
            "params": {"query": "SELECT 'search_verify' AS result"},
            "validate": _contains("search_verify"),
        },
    ],
}


class SandboxVerifier:
    """Runs verification checks on a sandbox using its registered agent tools."""

    def __init__(
        self,
        tool_registry: "AgentToolRegistry",
        instance_repo: "PluginInstanceRepo",
        docker_runtime: "DockerRuntime",
    ) -> None:
        self._tools = tool_registry
        self._repo = instance_repo
        self._docker = docker_runtime

    async def verify(
        self,
        sandbox_id: str,
        template_id: str | None = None,
        skip_cross_plugin: bool = False,
    ) -> VerifyResult:
        """Run all applicable verification checks for a sandbox."""
        start = time.monotonic()
        result = VerifyResult(sandbox_id=sandbox_id)
        log = logger.bind(sandbox_id=sandbox_id)
        log.info("verify_start")

        # Get installed plugins
        instances = await self._repo.list_instances(sandbox_id)
        installed_plugins = {
            inst["plugin_name"]: inst["plugin_id"]
            for inst in instances
        }

        # Phase 1: Per-plugin checks
        for plugin_name, plugin_id in installed_plugins.items():
            checks = PLUGIN_CHECKS.get(plugin_id, [])
            if not checks:
                result.steps.append(VerifyStepResult(
                    name="No checks defined",
                    plugin=plugin_name,
                    passed=True,
                    message=f"No verification checks for plugin type '{plugin_id}'",
                    category="plugin",
                ))
                result.total += 1
                result.skipped += 1
                continue

            for check in checks:
                step_result = await self._run_check(
                    sandbox_id, plugin_name, check, category="plugin",
                )
                result.steps.append(step_result)
                result.total += 1
                if step_result.passed:
                    result.passed += 1
                else:
                    result.failed += 1
                    # Stop this plugin's checks on first failure
                    break

        # Phase 2: Cross-plugin checks (if template is known)
        if not skip_cross_plugin and template_id:
            cross_checks = CROSS_PLUGIN_CHECKS.get(template_id, [])
            for check in cross_checks:
                # Verify the target plugin is installed
                target_plugin = check.get("plugin")
                if target_plugin not in installed_plugins:
                    result.steps.append(VerifyStepResult(
                        name=check["name"],
                        plugin=target_plugin or "unknown",
                        passed=True,
                        message=f"Skipped — plugin '{target_plugin}' not installed",
                        category="cross-plugin",
                    ))
                    result.total += 1
                    result.skipped += 1
                    continue

                step_result = await self._run_check(
                    sandbox_id, target_plugin, check, category="cross-plugin",
                )
                result.steps.append(step_result)
                result.total += 1
                if step_result.passed:
                    result.passed += 1
                else:
                    result.failed += 1

        elapsed = int((time.monotonic() - start) * 1000)
        result.duration_ms = elapsed
        log.info("verify_complete", passed=result.passed, failed=result.failed, total=result.total, ms=elapsed)
        return result

    async def _run_check(
        self,
        sandbox_id: str,
        plugin_name: str,
        check: dict[str, Any],
        category: str,
    ) -> VerifyStepResult:
        """Execute a single verification check."""
        step_start = time.monotonic()
        tool_name = check["tool"]
        params = check.get("params", {})
        validate_fn = check.get("validate", _no_error)

        tool = self._tools.get_tool(sandbox_id, tool_name)
        if not tool:
            return VerifyStepResult(
                name=check["name"],
                plugin=plugin_name,
                passed=False,
                message=f"Tool '{tool_name}' not found — plugin may not have registered tools",
                category=category,
            )

        try:
            output = await asyncio.wait_for(tool.handler(params), timeout=30)
            output_str = str(output) if output is not None else ""
            passed, message = validate_fn(output_str)
            elapsed = int((time.monotonic() - step_start) * 1000)
            return VerifyStepResult(
                name=check["name"],
                plugin=plugin_name,
                passed=passed,
                message=message,
                duration_ms=elapsed,
                output=output_str,
                category=category,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - step_start) * 1000)
            return VerifyStepResult(
                name=check["name"],
                plugin=plugin_name,
                passed=False,
                message="Timed out after 30s",
                duration_ms=elapsed,
                category=category,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - step_start) * 1000)
            return VerifyStepResult(
                name=check["name"],
                plugin=plugin_name,
                passed=False,
                message=f"Error: {e}",
                duration_ms=elapsed,
                output=str(e),
                category=category,
            )
