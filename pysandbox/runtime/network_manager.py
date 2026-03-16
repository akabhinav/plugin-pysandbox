"""Network management — thin wrapper around DockerRuntime for network ops."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pysandbox.runtime.docker_runtime import DockerRuntime


class NetworkManager:
    """Creates and removes per-sandbox Docker bridge networks."""

    def __init__(self, docker_runtime: "DockerRuntime") -> None:
        self._docker = docker_runtime

    async def create_sandbox_network(self, sandbox_id: str, prefix: str = "pysb") -> str:
        """Create an isolated bridge network for a sandbox."""
        name = f"{prefix}-{sandbox_id[:8]}"
        await self._docker.create_network(
            name=name,
            labels={"pysandbox.sandbox_id": sandbox_id},
        )
        return name

    async def remove_sandbox_network(self, sandbox_id: str, prefix: str = "pysb") -> None:
        name = f"{prefix}-{sandbox_id[:8]}"
        await self._docker.remove_network(name)
