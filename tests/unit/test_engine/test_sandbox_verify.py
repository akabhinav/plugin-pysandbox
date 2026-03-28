"""Tests for sandbox verification engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pysandbox.engine.sandbox_verify import SandboxVerifier, PLUGIN_CHECKS, CROSS_PLUGIN_CHECKS


@pytest.fixture
def tool_registry():
    registry = MagicMock()
    # Default: tools exist and return context-appropriate responses
    # Return values that pass all validators (contain expected strings)
    responses = {
        "sql_query": "1\nverify_ok\n2\ncross_plugin_verify",
        "sql_execute": "INSERT 0 1",
        "redis_set": "OK",
        "redis_get": "verify_ok\ncross_plugin_verify\ntrue",
        "redis_list_keys": "_verify_test",
        "kafka_create_topic": "Created topic",
        "kafka_list_topics": "_verify_test\ncross_verify",
        "kafka_produce": "OK",
        "kafka_delete_topic": "OK",
        "kafka_consume": "message",
        "s3_list": "buckets: []",
        "nessie_list_branches": "main",
        "es_cluster_health": "green",
        "clickhouse_query": "1\nsearch_verify",
        "cypher_query": "result",
        "mongo_insert": "OK",
        "mongo_find": "verify_ok",
    }

    def make_tool(tool_name):
        tool_mock = MagicMock()
        tool_mock.handler = AsyncMock(return_value=responses.get(tool_name, "OK"))
        return tool_mock

    registry.get_tool = MagicMock(side_effect=lambda sid, name: make_tool(name))
    return registry


@pytest.fixture
def instance_repo():
    repo = MagicMock()
    repo.list_instances = AsyncMock(return_value=[
        {"plugin_name": "postgres", "plugin_id": "postgres"},
        {"plugin_name": "redis", "plugin_id": "redis"},
    ])
    return repo


@pytest.fixture
def docker_runtime():
    return MagicMock()


@pytest.fixture
def verifier(tool_registry, instance_repo, docker_runtime):
    return SandboxVerifier(tool_registry, instance_repo, docker_runtime)


class TestSandboxVerifier:
    @pytest.mark.asyncio
    async def test_verify_basic(self, verifier):
        """Verification runs checks for installed plugins."""
        result = await verifier.verify("sb1")
        assert result.total > 0
        assert result.passed > 0
        assert result.failed == 0
        assert result.success

    @pytest.mark.asyncio
    async def test_verify_returns_dict(self, verifier):
        result = await verifier.verify("sb1")
        d = result.to_dict()
        assert d["sandbox_id"] == "sb1"
        assert d["success"] is True
        assert "steps" in d
        assert d["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_verify_tool_failure(self, verifier, tool_registry):
        """Failed tool execution marks step as failed."""
        fail_tool = MagicMock()
        fail_tool.handler = AsyncMock(side_effect=RuntimeError("connection refused"))
        tool_registry.get_tool = MagicMock(return_value=fail_tool)

        result = await verifier.verify("sb1")
        assert result.failed > 0
        assert not result.success

    @pytest.mark.asyncio
    async def test_verify_tool_not_found(self, verifier, tool_registry):
        """Missing tool is reported as failure."""
        tool_registry.get_tool = MagicMock(return_value=None)
        result = await verifier.verify("sb1")
        assert result.failed > 0

    @pytest.mark.asyncio
    async def test_verify_no_plugins(self, verifier, instance_repo):
        """Empty sandbox has no checks."""
        instance_repo.list_instances = AsyncMock(return_value=[])
        result = await verifier.verify("sb1")
        assert result.total == 0
        assert result.success is False  # 0 total = not success

    @pytest.mark.asyncio
    async def test_verify_unknown_plugin(self, verifier, instance_repo):
        """Plugin with no checks defined is skipped."""
        instance_repo.list_instances = AsyncMock(return_value=[
            {"plugin_name": "grafana", "plugin_id": "grafana"},
        ])
        result = await verifier.verify("sb1")
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_verify_with_template_cross_checks(self, verifier, instance_repo):
        """Cross-plugin checks run when template_id is provided."""
        instance_repo.list_instances = AsyncMock(return_value=[
            {"plugin_name": "postgres", "plugin_id": "postgres"},
            {"plugin_name": "redis", "plugin_id": "redis"},
            {"plugin_name": "kafka", "plugin_id": "kafka"},
        ])
        result = await verifier.verify("sb1", template_id="microservices")
        cross_steps = [s for s in result.steps if s.category == "cross-plugin"]
        assert len(cross_steps) > 0

    @pytest.mark.asyncio
    async def test_verify_skip_cross_plugin(self, verifier, instance_repo):
        """skip_cross_plugin=True skips cross-plugin checks."""
        instance_repo.list_instances = AsyncMock(return_value=[
            {"plugin_name": "postgres", "plugin_id": "postgres"},
            {"plugin_name": "redis", "plugin_id": "redis"},
            {"plugin_name": "kafka", "plugin_id": "kafka"},
        ])
        result = await verifier.verify("sb1", template_id="microservices", skip_cross_plugin=True)
        cross_steps = [s for s in result.steps if s.category == "cross-plugin"]
        assert len(cross_steps) == 0

    @pytest.mark.asyncio
    async def test_verify_cross_check_missing_plugin(self, verifier, instance_repo):
        """Cross checks skip if target plugin not installed."""
        # Only postgres installed, but microservices needs redis+kafka too
        instance_repo.list_instances = AsyncMock(return_value=[
            {"plugin_name": "postgres", "plugin_id": "postgres"},
        ])
        result = await verifier.verify("sb1", template_id="microservices")
        skipped_cross = [s for s in result.steps if s.category == "cross-plugin" and "Skipped" in s.message]
        assert len(skipped_cross) > 0

    @pytest.mark.asyncio
    async def test_verify_timeout(self, verifier, tool_registry):
        """Tool timeout is handled gracefully."""
        import asyncio
        slow_tool = MagicMock()

        async def slow_handler(params):
            await asyncio.sleep(60)

        slow_tool.handler = slow_handler
        tool_registry.get_tool = MagicMock(return_value=slow_tool)

        result = await verifier.verify("sb1")
        assert result.failed > 0


class TestPluginCheckDefinitions:
    def test_postgres_checks_defined(self):
        assert "postgres" in PLUGIN_CHECKS
        assert len(PLUGIN_CHECKS["postgres"]) >= 3

    def test_redis_checks_defined(self):
        assert "redis" in PLUGIN_CHECKS
        assert len(PLUGIN_CHECKS["redis"]) >= 2

    def test_kafka_checks_defined(self):
        assert "kafka" in PLUGIN_CHECKS
        assert len(PLUGIN_CHECKS["kafka"]) >= 3

    def test_all_checks_have_required_keys(self):
        for plugin_id, checks in PLUGIN_CHECKS.items():
            for check in checks:
                assert "name" in check, f"Missing 'name' in {plugin_id}"
                assert "tool" in check, f"Missing 'tool' in {plugin_id}"
                assert "validate" in check, f"Missing 'validate' in {plugin_id}"
                assert callable(check["validate"])


class TestCrossPluginChecks:
    def test_microservices_cross_checks(self):
        assert "microservices" in CROSS_PLUGIN_CHECKS
        checks = CROSS_PLUGIN_CHECKS["microservices"]
        plugins_used = {c["plugin"] for c in checks}
        assert "postgres" in plugins_used
        assert "redis" in plugins_used
        assert "kafka" in plugins_used

    def test_event_driven_cross_checks(self):
        assert "event-driven" in CROSS_PLUGIN_CHECKS

    def test_all_cross_checks_have_plugin_field(self):
        for template_id, checks in CROSS_PLUGIN_CHECKS.items():
            for check in checks:
                assert "plugin" in check, f"Missing 'plugin' in {template_id} check"
                assert "tool" in check, f"Missing 'tool' in {template_id} check"
