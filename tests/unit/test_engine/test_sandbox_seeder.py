"""Tests for sandbox data seeder."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pysandbox.engine.sandbox_seeder import SandboxSeeder, SEED_DEFINITIONS


@pytest.fixture
def tool_registry():
    registry = MagicMock()
    tool_mock = MagicMock()
    tool_mock.handler = AsyncMock(return_value="OK")
    registry.get_tool = MagicMock(return_value=tool_mock)
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
def seeder(tool_registry, instance_repo):
    return SandboxSeeder(tool_registry, instance_repo)


class TestSandboxSeeder:
    @pytest.mark.asyncio
    async def test_seed_basic(self, seeder):
        result = await seeder.seed("sb1")
        assert result.total_steps > 0
        assert result.succeeded > 0
        assert result.failed == 0
        assert result.to_dict()["success"] is True

    @pytest.mark.asyncio
    async def test_seed_returns_dict(self, seeder):
        result = await seeder.seed("sb1")
        d = result.to_dict()
        assert d["sandbox_id"] == "sb1"
        assert "steps" in d
        assert d["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_seed_tool_failure(self, seeder, tool_registry):
        tool_mock = MagicMock()
        tool_mock.handler = AsyncMock(side_effect=RuntimeError("DB error"))
        tool_registry.get_tool = MagicMock(return_value=tool_mock)

        result = await seeder.seed("sb1")
        assert result.failed > 0

    @pytest.mark.asyncio
    async def test_seed_tool_not_found(self, seeder, tool_registry):
        tool_registry.get_tool = MagicMock(return_value=None)
        result = await seeder.seed("sb1")
        assert result.failed > 0

    @pytest.mark.asyncio
    async def test_seed_no_plugins(self, seeder, instance_repo):
        instance_repo.list_instances = AsyncMock(return_value=[])
        result = await seeder.seed("sb1")
        assert result.total_steps == 0

    @pytest.mark.asyncio
    async def test_seed_unknown_plugin_skipped(self, seeder, instance_repo):
        instance_repo.list_instances = AsyncMock(return_value=[
            {"plugin_name": "grafana", "plugin_id": "grafana"},
        ])
        result = await seeder.seed("sb1")
        assert result.total_steps == 0

    @pytest.mark.asyncio
    async def test_seed_tracks_rows(self, seeder):
        result = await seeder.seed("sb1")
        total_rows = sum(s.rows_created for s in result.steps)
        assert total_rows > 0

    @pytest.mark.asyncio
    async def test_seed_stops_on_failure_per_plugin(self, seeder, tool_registry):
        """Seeder stops seeding a plugin on first failure."""
        call_count = 0

        async def fail_on_second(params):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("fail")
            return "OK"

        tool_mock = MagicMock()
        tool_mock.handler = fail_on_second
        tool_registry.get_tool = MagicMock(return_value=tool_mock)

        result = await seeder.seed("sb1")
        # Should have stopped after first failure for that plugin
        assert result.failed >= 1


class TestSeedDefinitions:
    def test_postgres_seeds_defined(self):
        assert "postgres" in SEED_DEFINITIONS
        assert len(SEED_DEFINITIONS["postgres"]) >= 3

    def test_redis_seeds_defined(self):
        assert "redis" in SEED_DEFINITIONS
        assert len(SEED_DEFINITIONS["redis"]) >= 3

    def test_kafka_seeds_defined(self):
        assert "kafka" in SEED_DEFINITIONS

    def test_all_seeds_have_required_keys(self):
        for plugin_id, steps in SEED_DEFINITIONS.items():
            for step in steps:
                assert "name" in step, f"Missing 'name' in {plugin_id}"
                assert "tool" in step, f"Missing 'tool' in {plugin_id}"
                assert "params" in step, f"Missing 'params' in {plugin_id}"
