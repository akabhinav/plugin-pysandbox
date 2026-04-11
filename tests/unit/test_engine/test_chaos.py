"""Tests for ChaosEngine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.chaos import ChaosEngine, ChaosRegistry


@pytest.fixture
def docker_runtime():
    rt = MagicMock()
    rt.stop = AsyncMock()
    rt.exec_in_container = AsyncMock(return_value="")
    # Expose a stub client for _docker_cmd / _docker_update
    client = MagicMock()
    container = MagicMock()
    client.containers.get.return_value = container
    # The raw low-level `client.api` is used by the NanoCPUs path.
    api = MagicMock()
    api._url = MagicMock(side_effect=lambda path: f"http://localhost{path}")
    api._post_json = MagicMock(return_value=MagicMock(status_code=200))
    api._raise_for_status = MagicMock()
    client.api = api
    rt._get_client = MagicMock(return_value=client)
    rt._client = client
    rt._captured_container = container
    rt._captured_api = api
    return rt


@pytest.fixture
def instance_repo():
    repo = MagicMock()
    repo.get_instance = AsyncMock(return_value={
        "plugin_name": "redis",
        "plugin_id": "redis",
        "container_id": "c" * 64,
    })
    return repo


@pytest.fixture
def engine(docker_runtime, instance_repo):
    return ChaosEngine(docker_runtime, instance_repo)


class TestChaosKill:
    @pytest.mark.asyncio
    async def test_immediate_kill_stops_container(self, engine, docker_runtime):
        result = await engine.kill("sb-1", "redis", after_seconds=0)
        docker_runtime.stop.assert_awaited_once()
        assert result["fault_type"] == "kill"
        assert result["plugin_name"] == "redis"

    @pytest.mark.asyncio
    async def test_scheduled_kill_is_recorded_immediately(self, engine, docker_runtime):
        result = await engine.kill("sb-1", "redis", after_seconds=0.01)
        # Call returns quickly even though the actual stop is deferred.
        assert result["fault_type"] == "kill"
        assert result["params"]["after_seconds"] == 0.01
        # Give the scheduled task a chance to run.
        await asyncio.sleep(0.05)
        docker_runtime.stop.assert_awaited()


class TestChaosPause:
    @pytest.mark.asyncio
    async def test_pause_invokes_docker_pause(self, engine, docker_runtime):
        result = await engine.pause("sb-1", "redis")
        docker_runtime._captured_container.pause.assert_called_once()
        assert result["fault_type"] == "pause"

    @pytest.mark.asyncio
    async def test_unpause_removes_injection_from_registry(self, engine, docker_runtime):
        await engine.pause("sb-1", "redis")
        assert len(await engine.list_active("sb-1")) == 1
        result = await engine.unpause("sb-1", "redis")
        assert len(result["removed"]) == 1
        assert len(await engine.list_active("sb-1")) == 0


class TestChaosLatency:
    @pytest.mark.asyncio
    async def test_latency_shells_out_to_tc(self, engine, docker_runtime):
        await engine.latency("sb-1", "redis", delay_ms=200)
        cmd = docker_runtime.exec_in_container.call_args[0][1]
        assert "netem delay 200ms" in cmd
        assert "tc qdisc del" in cmd  # clears prior rule first

    @pytest.mark.asyncio
    async def test_latency_with_jitter(self, engine, docker_runtime):
        await engine.latency("sb-1", "redis", delay_ms=50, jitter_ms=10)
        cmd = docker_runtime.exec_in_container.call_args[0][1]
        assert "50ms 10ms" in cmd

    @pytest.mark.asyncio
    async def test_packet_loss(self, engine, docker_runtime):
        await engine.packet_loss("sb-1", "redis", loss_percent=5.0)
        cmd = docker_runtime.exec_in_container.call_args[0][1]
        assert "netem loss 5.0%" in cmd


class TestChaosThrottle:
    @pytest.mark.asyncio
    async def test_cpu_throttle_posts_nanocpus_via_raw_api(self, engine, docker_runtime):
        await engine.cpu_throttle("sb-1", "redis", cpus=0.5)
        # We use the low-level HTTP client directly because docker-py's
        # high-level `container.update()` doesn't accept nano_cpus and
        # Docker refuses cpu_period/cpu_quota on containers created with
        # NanoCPUs. The chaos engine sends a raw POST with NanoCPUs set.
        docker_runtime._captured_api._post_json.assert_called_once()
        call = docker_runtime._captured_api._post_json.call_args
        assert "/containers/" in call.args[0]
        assert "/update" in call.args[0]
        assert call.kwargs["data"] == {"NanoCPUs": 500_000_000}

    @pytest.mark.asyncio
    async def test_memory_throttle_calls_container_update(self, engine, docker_runtime):
        await engine.memory_throttle("sb-1", "redis", memory_mb=256)
        kwargs = docker_runtime._captured_container.update.call_args.kwargs
        assert kwargs["mem_limit"] == 256 * 1024 * 1024


class TestChaosReset:
    @pytest.mark.asyncio
    async def test_reset_rolls_back_every_active_injection(self, engine, docker_runtime):
        await engine.latency("sb-1", "redis", delay_ms=100)
        await engine.pause("sb-1", "redis")
        assert len(await engine.list_active("sb-1")) == 2
        result = await engine.reset("sb-1")
        assert result["reset_count"] == 2
        assert len(await engine.list_active("sb-1")) == 0

    @pytest.mark.asyncio
    async def test_reset_returns_errors_without_losing_registry(
        self, engine, docker_runtime,
    ):
        # Make unpause blow up so reset must record the error.
        docker_runtime._captured_container.unpause = MagicMock(side_effect=RuntimeError("boom"))
        await engine.pause("sb-1", "redis")
        result = await engine.reset("sb-1")
        assert len(result["errors"]) == 1
        # Registry is still drained even if undo failed, so a retry doesn't
        # double-undo.
        assert len(await engine.list_active("sb-1")) == 0

    @pytest.mark.asyncio
    async def test_unknown_plugin_raises_value_error(self, engine, instance_repo):
        instance_repo.get_instance = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await engine.kill("sb-1", "ghost")

    @pytest.mark.asyncio
    async def test_plugin_without_container_id_raises(self, engine, instance_repo):
        instance_repo.get_instance = AsyncMock(return_value={
            "plugin_name": "redis",
            "container_id": None,
        })
        with pytest.raises(ValueError, match="no container"):
            await engine.pause("sb-1", "redis")


class TestRegistry:
    def test_registry_lifecycle(self):
        from pysandbox.engine.chaos import ChaosInjection
        r = ChaosRegistry()
        inj = ChaosInjection(
            id="x", sandbox_id="sb", plugin_name="p", container_id="c",
            fault_type="pause", params={}, started_at="now",
        )
        r.add(inj)
        assert len(r.list_for("sb")) == 1
        assert r.remove("sb", "x") is inj
        assert r.list_for("sb") == []
