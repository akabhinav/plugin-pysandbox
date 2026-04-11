"""Tests for SandboxBrancher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.branching import SandboxBranchError, SandboxBrancher


@pytest.fixture
def source_sandbox():
    return {
        "id": "src-abc123",
        "name": "prod-db",
        "status": "running",
        "tags": {"env": "prod"},
    }


@pytest.fixture
def source_instances():
    return [
        {
            "sandbox_id": "src-abc123",
            "plugin_id": "postgres",
            "plugin_name": "db",
            "version": "16",
            "config": {"db": "app"},
            "startup_order": 50,
        },
        {
            "sandbox_id": "src-abc123",
            "plugin_id": "redis",
            "plugin_name": "cache",
            "version": "7",
            "config": {},
            "startup_order": 60,
        },
    ]


@pytest.fixture
def new_instances():
    return [
        {
            "sandbox_id": "new-def456",
            "plugin_id": "postgres",
            "plugin_name": "db",
            "version": "16",
            "config": {"db": "app"},
        },
        {
            "sandbox_id": "new-def456",
            "plugin_id": "redis",
            "plugin_name": "cache",
            "version": "7",
            "config": {},
        },
    ]


@pytest.fixture
def sandbox_engine(source_sandbox):
    engine = MagicMock()
    engine.get = AsyncMock(return_value=source_sandbox)
    engine.create = AsyncMock(return_value={
        "id": "new-def456",
        "name": "feature-x",
        "status": "running",
        "docker_network": "pysb-new-def4",
        "dns_zone": "new-def4.sandbox.local",
        "tags": {},
    })
    engine.pause = AsyncMock()
    engine.resume = AsyncMock()
    return engine


@pytest.fixture
def instance_repo(source_instances, new_instances):
    repo = MagicMock()

    async def list_instances(sid):
        if sid == "src-abc123":
            return source_instances
        return new_instances

    repo.list_instances = AsyncMock(side_effect=list_instances)
    return repo


@pytest.fixture
def docker_runtime():
    rt = MagicMock()
    client = MagicMock()
    client.containers.run = MagicMock()
    rt._get_client = MagicMock(return_value=client)
    rt._captured_client = client
    return rt


@pytest.fixture
def brancher(sandbox_engine, instance_repo, docker_runtime):
    return SandboxBrancher(sandbox_engine, instance_repo, docker_runtime)


class TestBranchCreate:
    @pytest.mark.asyncio
    async def test_new_sandbox_has_same_plugin_shape(
        self, brancher, sandbox_engine, source_instances,
    ):
        await brancher.branch("src-abc123", new_name="feature-x")

        call_kwargs = sandbox_engine.create.call_args.kwargs
        plugin_ids = [p["plugin_id"] for p in call_kwargs["plugins"]]
        plugin_names = [p["name"] for p in call_kwargs["plugins"]]
        assert plugin_ids == ["postgres", "redis"]
        assert plugin_names == ["db", "cache"]

    @pytest.mark.asyncio
    async def test_tags_merged_with_source(self, brancher, sandbox_engine):
        await brancher.branch(
            "src-abc123", new_name="feature-x", tags={"ticket": "ENG-42"},
        )
        tags = sandbox_engine.create.call_args.kwargs["tags"]
        assert tags["env"] == "prod"
        assert tags["ticket"] == "ENG-42"
        assert tags["branched_from"] == "src-abc123"

    @pytest.mark.asyncio
    async def test_missing_source_raises(self, brancher, sandbox_engine):
        sandbox_engine.get = AsyncMock(return_value=None)
        with pytest.raises(SandboxBranchError, match="not found"):
            await brancher.branch("ghost", new_name="x")

    @pytest.mark.asyncio
    async def test_source_without_plugins_raises(
        self, brancher, instance_repo,
    ):
        instance_repo.list_instances = AsyncMock(return_value=[])
        with pytest.raises(SandboxBranchError, match="no installed plugins"):
            await brancher.branch("src-abc123", new_name="x")


class TestBranchVolumeCopy:
    @pytest.mark.asyncio
    async def test_pause_and_resume_bookend_copy(self, brancher, sandbox_engine):
        await brancher.branch("src-abc123", new_name="feature-x")
        sandbox_engine.pause.assert_awaited_with("src-abc123")
        sandbox_engine.resume.assert_awaited_with("src-abc123")

    @pytest.mark.asyncio
    async def test_resume_runs_even_if_copy_fails(
        self, brancher, sandbox_engine, docker_runtime,
    ):
        docker_runtime._captured_client.containers.run.side_effect = RuntimeError("nope")
        result = await brancher.branch("src-abc123", new_name="feature-x")
        # Copy failures are recorded in the volumes_copied list,
        # not raised — and the source MUST be resumed afterward.
        sandbox_engine.resume.assert_awaited()
        assert any(v["status"] == "error" for v in result["volumes_copied"])

    @pytest.mark.asyncio
    async def test_copy_data_false_skips_volume_copy(
        self, brancher, sandbox_engine, docker_runtime,
    ):
        result = await brancher.branch(
            "src-abc123", new_name="feature-x", copy_data=False,
        )
        docker_runtime._captured_client.containers.run.assert_not_called()
        sandbox_engine.pause.assert_not_called()
        sandbox_engine.resume.assert_not_called()
        assert result["volumes_copied"] == []

    @pytest.mark.asyncio
    async def test_volume_copy_uses_deterministic_names(
        self, brancher, docker_runtime,
    ):
        await brancher.branch("src-abc123", new_name="feature-x")
        # At least one alpine-backed copy run was scheduled.
        calls = docker_runtime._captured_client.containers.run.call_args_list
        assert len(calls) == 2
        first_volumes = calls[0].kwargs["volumes"]
        # Volume names follow `pysb-{sid[:8]}-{plugin_name}`.
        assert any("pysb-src-abc1" in k for k in first_volumes.keys())
        assert any("pysb-new-def4" in k for k in first_volumes.keys())


class TestBranchResult:
    @pytest.mark.asyncio
    async def test_result_includes_source_id_and_volumes_copied(self, brancher):
        result = await brancher.branch("src-abc123", new_name="feature-x")
        assert result["source_sandbox_id"] == "src-abc123"
        assert len(result["volumes_copied"]) == 2
        assert all("plugin_name" in v for v in result["volumes_copied"])
