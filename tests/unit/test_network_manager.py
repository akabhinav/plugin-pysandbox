"""Tests for network manager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.runtime.network_manager import NetworkManager


@pytest.fixture
def mock_docker():
    docker = MagicMock()
    docker.create_network = AsyncMock(return_value="net-id")
    docker.remove_network = AsyncMock()
    return docker


class TestNetworkManager:
    @pytest.mark.asyncio
    async def test_create_sandbox_network(self, mock_docker):
        nm = NetworkManager(mock_docker)
        name = await nm.create_sandbox_network("abcdef12-3456-7890")
        assert name == "pysb-abcdef12"
        mock_docker.create_network.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_custom_prefix(self, mock_docker):
        nm = NetworkManager(mock_docker)
        name = await nm.create_sandbox_network("abcdef12-3456", prefix="test")
        assert name == "test-abcdef12"

    @pytest.mark.asyncio
    async def test_remove_sandbox_network(self, mock_docker):
        nm = NetworkManager(mock_docker)
        await nm.remove_sandbox_network("abcdef12-3456")
        mock_docker.remove_network.assert_called_once_with("pysb-abcdef12")
