"""Agent lifecycle management — start, stop, destroy per sandbox."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pysandbox.runtime.docker_runtime import DockerRuntime

logger = structlog.get_logger()


class AgentRuntime:
    """Manages the agent container per sandbox."""

    def __init__(self, docker_runtime: "DockerRuntime", agent_image: str) -> None:
        self._docker = docker_runtime
        self._image = agent_image
        # sandbox_id → container_id
        self._agents: dict[str, str] = {}

    async def start(self, sandbox_id: str, network: str, dns_zone: str) -> str | None:
        """Start agent container in the sandbox network."""
        container_name = f"pysb-{sandbox_id[:8]}-agent"

        try:
            container_id = await self._docker.create_and_start(
                container_name=container_name,
                network=network,
                network_alias="agent",
                host_port=None,
                container_port=0,
                docker_config={
                    "image": self._image,
                    "environment": {
                        "SANDBOX_ID": sandbox_id,
                        "DNS_ZONE": dns_zone,
                    },
                },
            )
            self._agents[sandbox_id] = container_id
            logger.info("agent_started", sandbox_id=sandbox_id)
            return container_id
        except Exception:
            logger.warning("agent_start_skipped", sandbox_id=sandbox_id, reason="image_unavailable")
            return None

    async def stop(self, sandbox_id: str) -> None:
        container_id = self._agents.get(sandbox_id)
        if container_id:
            await self._docker.stop(container_id)
            logger.info("agent_stopped", sandbox_id=sandbox_id)

    async def destroy(self, sandbox_id: str) -> None:
        container_id = self._agents.pop(sandbox_id, None)
        if container_id:
            await self._docker.stop(container_id)
            await self._docker.remove(container_id, force=True)
            logger.info("agent_destroyed", sandbox_id=sandbox_id)

    def is_running(self, sandbox_id: str) -> bool:
        return sandbox_id in self._agents

    def get_container_id(self, sandbox_id: str) -> str | None:
        return self._agents.get(sandbox_id)
