"""Tests for TimeTravelEngine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.time_travel import TimeTravelEngine, TimeTravelError


@pytest.fixture
def source_sandbox():
    return {"id": "sb-abc123", "status": "running"}


@pytest.fixture
def source_instances():
    return [
        {
            "sandbox_id": "sb-abc123",
            "plugin_id": "postgres",
            "plugin_name": "db",
        },
        {
            "sandbox_id": "sb-abc123",
            "plugin_id": "redis",
            "plugin_name": "cache",
        },
    ]


@pytest.fixture
def sandbox_engine(source_sandbox):
    engine = MagicMock()
    engine.get = AsyncMock(return_value=source_sandbox)
    engine.pause = AsyncMock()
    engine.resume = AsyncMock()
    return engine


@pytest.fixture
def instance_repo(source_instances):
    repo = MagicMock()
    repo.list_instances = AsyncMock(return_value=source_instances)
    return repo


@pytest.fixture
def docker_runtime():
    rt = MagicMock()
    client = MagicMock()
    client.containers.run = MagicMock()
    rt._get_client = MagicMock(return_value=client)
    rt._captured_client = client
    rt.remove_volume = AsyncMock()
    return rt


@pytest.fixture
def tt(sandbox_engine, instance_repo, docker_runtime):
    return TimeTravelEngine(
        sandbox_engine, instance_repo, docker_runtime,
        max_snapshots_per_sandbox=3,
    )


class TestCapture:
    @pytest.mark.asyncio
    async def test_capture_snapshots_every_plugin_volume(
        self, tt, docker_runtime,
    ):
        result = await tt.capture("sb-abc123", label="before-migration")
        assert result["volume_count"] == 2
        assert result["label"] == "before-migration"
        # Two alpine copy containers were invoked.
        assert docker_runtime._captured_client.containers.run.call_count == 2

    @pytest.mark.asyncio
    async def test_capture_pauses_and_resumes_sandbox(self, tt, sandbox_engine):
        await tt.capture("sb-abc123")
        sandbox_engine.pause.assert_awaited_with("sb-abc123")
        sandbox_engine.resume.assert_awaited_with("sb-abc123")

    @pytest.mark.asyncio
    async def test_capture_does_not_double_pause_already_paused(
        self, tt, sandbox_engine,
    ):
        sandbox_engine.get = AsyncMock(return_value={"id": "sb-abc123", "status": "paused"})
        await tt.capture("sb-abc123")
        sandbox_engine.pause.assert_not_called()
        sandbox_engine.resume.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_sandbox_raises(self, tt, sandbox_engine):
        sandbox_engine.get = AsyncMock(return_value=None)
        with pytest.raises(TimeTravelError, match="not found"):
            await tt.capture("ghost")

    @pytest.mark.asyncio
    async def test_ring_buffer_eviction(self, tt):
        # max_snapshots_per_sandbox=3
        for _ in range(5):
            await tt.capture("sb-abc123")
        snaps = tt.list_snapshots("sb-abc123")
        assert len(snaps) == 3

    @pytest.mark.asyncio
    async def test_volume_copy_failure_does_not_abort_capture(
        self, tt, docker_runtime,
    ):
        # First volume copy fails, second succeeds.
        call_count = {"n": 0}

        def maybe_fail(*a, **k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("disk full")

        docker_runtime._captured_client.containers.run.side_effect = maybe_fail
        result = await tt.capture("sb-abc123")
        # One volume made it in; the other was skipped.
        assert result["volume_count"] == 1


class TestRewind:
    @pytest.mark.asyncio
    async def test_rewind_restores_each_volume(
        self, tt, docker_runtime, sandbox_engine,
    ):
        snap = await tt.capture("sb-abc123")
        # Reset the call counter so we can see what rewind does.
        docker_runtime._captured_client.containers.run.reset_mock()
        result = await tt.rewind("sb-abc123", snap["id"])
        assert len(result["restored"]) == 2
        assert all(r["status"] == "ok" for r in result["restored"])
        # Each restore triggers another cp container.
        assert docker_runtime._captured_client.containers.run.call_count == 2

    @pytest.mark.asyncio
    async def test_rewind_unknown_snapshot_raises(self, tt):
        await tt.capture("sb-abc123")
        with pytest.raises(TimeTravelError, match="not found"):
            await tt.rewind("sb-abc123", "snap-missing")

    @pytest.mark.asyncio
    async def test_rewind_unknown_sandbox_raises(self, tt, sandbox_engine):
        snap = await tt.capture("sb-abc123")
        sandbox_engine.get = AsyncMock(return_value=None)
        with pytest.raises(TimeTravelError):
            await tt.rewind("ghost", snap["id"])


class TestListAndDelete:
    @pytest.mark.asyncio
    async def test_list_newest_first(self, tt):
        first = await tt.capture("sb-abc123", label="first")
        second = await tt.capture("sb-abc123", label="second")
        snaps = tt.list_snapshots("sb-abc123")
        assert snaps[0]["id"] == second["id"]
        assert snaps[1]["id"] == first["id"]

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, tt, docker_runtime):
        snap = await tt.capture("sb-abc123")
        ok = await tt.delete_snapshot("sb-abc123", snap["id"])
        assert ok is True
        assert tt.list_snapshots("sb-abc123") == []
        # Remove volume called at least once per captured volume.
        assert docker_runtime.remove_volume.await_count >= 1

    @pytest.mark.asyncio
    async def test_delete_missing_snapshot_returns_false(self, tt):
        assert await tt.delete_snapshot("sb-abc123", "snap-missing") is False


class TestAutoCapture:
    @pytest.mark.asyncio
    async def test_auto_capture_starts_and_stops(self, tt):
        await tt.start_auto_capture("sb-abc123", interval_seconds=30)
        # Starting twice is a no-op.
        await tt.start_auto_capture("sb-abc123", interval_seconds=30)
        stopped = await tt.stop_auto_capture("sb-abc123")
        assert stopped is True
        # Stopping twice returns False.
        assert await tt.stop_auto_capture("sb-abc123") is False

    @pytest.mark.asyncio
    async def test_auto_capture_runs_at_least_once(self, tt):
        # Drop interval to nearly zero for the test.
        await tt.start_auto_capture("sb-abc123", interval_seconds=1)
        # Give the loop a moment to run its first iteration.
        await asyncio.sleep(0.1)
        await tt.stop_auto_capture("sb-abc123")
        snaps = tt.list_snapshots("sb-abc123")
        assert len(snaps) >= 1
