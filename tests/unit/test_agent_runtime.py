"""Tests for agent runtime."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.agent.agent_runtime import AgentRuntime


@pytest.fixture
def mock_docker():
    docker = MagicMock()
    docker.create_and_start = AsyncMock(return_value="agent-container-1")
    docker.stop = AsyncMock()
    docker.remove = AsyncMock()
    return docker


@pytest.fixture
def agent_runtime(mock_docker):
    return AgentRuntime(mock_docker, "pysandbox/pyoz:latest")


class TestAgentRuntime:
    @pytest.mark.asyncio
    async def test_start_agent(self, agent_runtime, mock_docker):
        cid = await agent_runtime.start("sb1", "pysb-sb1", "abc.sandbox.local")
        assert cid == "agent-container-1"
        assert agent_runtime.is_running("sb1")
        mock_docker.create_and_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_agent(self, agent_runtime, mock_docker):
        await agent_runtime.start("sb1", "net", "zone")
        await agent_runtime.stop("sb1")
        mock_docker.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_destroy_agent(self, agent_runtime, mock_docker):
        await agent_runtime.start("sb1", "net", "zone")
        await agent_runtime.destroy("sb1")
        assert not agent_runtime.is_running("sb1")
        mock_docker.remove.assert_called()

    @pytest.mark.asyncio
    async def test_not_running_before_start(self, agent_runtime):
        assert not agent_runtime.is_running("sb1")

    @pytest.mark.asyncio
    async def test_get_container_id(self, agent_runtime, mock_docker):
        await agent_runtime.start("sb1", "net", "zone")
        assert agent_runtime.get_container_id("sb1") == "agent-container-1"

    @pytest.mark.asyncio
    async def test_get_container_id_none(self, agent_runtime):
        assert agent_runtime.get_container_id("sb1") is None

    @pytest.mark.asyncio
    async def test_start_failure_handled(self, agent_runtime, mock_docker):
        """Image not available doesn't crash."""
        mock_docker.create_and_start = AsyncMock(side_effect=RuntimeError("image not found"))
        result = await agent_runtime.start("sb1", "net", "zone")
        assert result is None
        assert not agent_runtime.is_running("sb1")

    @pytest.mark.asyncio
    async def test_stop_nonexistent_is_noop(self, agent_runtime, mock_docker):
        await agent_runtime.stop("nonexistent")
        mock_docker.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_destroy_nonexistent_is_noop(self, agent_runtime, mock_docker):
        await agent_runtime.destroy("nonexistent")
        mock_docker.stop.assert_not_called()
