"""Docker container and network management via docker-py SDK."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


class DockerRuntime:
    """Manages Docker containers and networks for sandboxes.

    All operations are async (run in executor) to avoid blocking the event loop.
    """

    def __init__(self, docker_socket: str = "unix:///var/run/docker.sock") -> None:
        self._socket = docker_socket
        self._client = None

    def _get_client(self):
        """Lazy-init Docker client."""
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    async def create_network(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Create a Docker bridge network. Returns network ID."""
        def _create():
            client = self._get_client()
            network = client.networks.create(
                name=name,
                driver="bridge",
                labels=labels or {},
                check_duplicate=True,
            )
            return network.id

        network_id = await asyncio.to_thread(_create)
        logger.info("docker_network_created", name=name, id=network_id[:12])
        return network_id

    async def remove_network(self, name: str) -> None:
        """Remove a Docker network by name."""
        def _remove():
            client = self._get_client()
            try:
                network = client.networks.get(name)
                network.remove()
            except Exception:
                logger.warning("network_remove_failed", name=name)

        await asyncio.to_thread(_remove)

    async def create_and_start(
        self,
        container_name: str,
        network: str,
        network_alias: str,
        host_port: int | None,
        container_port: int,
        docker_config: dict[str, Any],
        cpu_limit: float = 1.0,
        memory_limit: str = "512m",
    ) -> str:
        """Create and start a container. Returns container ID."""
        def _create():
            client = self._get_client()

            # Build port bindings
            ports = {}
            if host_port and container_port:
                ports[f"{container_port}/tcp"] = host_port

            # Extract config
            image = docker_config.get("image", "")
            environment = docker_config.get("environment", {})
            volumes = docker_config.get("volumes", {})
            command = docker_config.get("command")
            healthcheck = docker_config.get("healthcheck")

            # Parse memory limit
            mem_bytes = _parse_memory_bytes(memory_limit)

            container = client.containers.run(
                image=image,
                name=container_name,
                detach=True,
                environment=environment,
                volumes=volumes,
                command=command,
                ports=ports,
                healthcheck=healthcheck,
                network=network,
                nano_cpus=int(cpu_limit * 1e9),
                mem_limit=mem_bytes,
                labels={
                    "pysandbox.managed": "true",
                    "pysandbox.container_name": container_name,
                },
                restart_policy={"Name": "unless-stopped"},
            )

            # Add network alias
            try:
                net = client.networks.get(network)
                net.connect(container, aliases=[network_alias])
            except Exception:
                pass  # Already connected via network param

            return container.id

        container_id = await asyncio.to_thread(_create)
        logger.info("container_started", name=container_name, id=container_id[:12])
        return container_id

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        def _stop():
            client = self._get_client()
            try:
                container = client.containers.get(container_id)
                container.stop(timeout=timeout)
            except Exception:
                logger.warning("container_stop_failed", id=container_id[:12])

        await asyncio.to_thread(_stop)

    async def start(self, container_id: str) -> None:
        def _start():
            client = self._get_client()
            container = client.containers.get(container_id)
            container.start()

        await asyncio.to_thread(_start)

    async def remove(self, container_id: str, force: bool = False) -> None:
        def _remove():
            client = self._get_client()
            try:
                container = client.containers.get(container_id)
                container.remove(force=force)
            except Exception:
                logger.warning("container_remove_failed", id=container_id[:12])

        await asyncio.to_thread(_remove)

    async def exec_in_container(self, container_id: str, command: str) -> str:
        """Run a shell command inside a container. Returns stdout."""
        def _exec():
            client = self._get_client()
            container = client.containers.get(container_id)
            exit_code, output = container.exec_run(
                ["sh", "-c", command], demux=True,
            )
            stdout = (output[0] or b"").decode() if isinstance(output, tuple) else (output or b"").decode()
            if exit_code != 0:
                logger.warning("exec_non_zero", container=container_id[:12], cmd=command[:80], code=exit_code)
            return stdout

        return await asyncio.to_thread(_exec)

    async def is_healthy(self, container_id: str) -> bool:
        """Check if a container's health status is 'healthy'."""
        return (await self.get_container_status(container_id)) == "healthy"

    async def get_container_status(self, container_id: str) -> str:
        """Get container health or run status.

        Returns 'healthy', 'unhealthy', 'starting', 'running' (no healthcheck),
        or Docker state like 'exited', 'dead', etc.
        """
        def _check():
            client = self._get_client()
            try:
                container = client.containers.get(container_id)
                container.reload()
                state = container.attrs.get("State", {})
                health = state.get("Health", {})
                if health:
                    return health.get("Status", "unknown")
                return state.get("Status", "unknown")
            except Exception:
                return "unknown"

        return await asyncio.to_thread(_check)

    async def get_container_ip(self, container_id: str, network: str) -> str:
        """Get the container's IP address on a specific network."""
        def _get_ip():
            client = self._get_client()
            container = client.containers.get(container_id)
            container.reload()
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            net_info = networks.get(network, {})
            return net_info.get("IPAddress", "")

        return await asyncio.to_thread(_get_ip)

    async def get_logs(self, container_id: str, tail: int = 100) -> str:
        def _logs():
            client = self._get_client()
            container = client.containers.get(container_id)
            return container.logs(tail=tail).decode()

        return await asyncio.to_thread(_logs)

    async def list_managed_containers(self) -> list[dict]:
        """List all pysandbox-managed containers."""
        def _list():
            client = self._get_client()
            containers = client.containers.list(
                all=True, filters={"label": "pysandbox.managed=true"},
            )
            result = []
            for c in containers:
                ports = c.attrs.get("NetworkSettings", {}).get("Ports", {})
                host_port = None
                for port_info in ports.values():
                    if port_info:
                        host_port = port_info[0].get("HostPort")
                        break
                result.append({
                    "id": c.id,
                    "short_id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:20],
                    "status": c.status,
                    "host_port": host_port,
                    "created": c.attrs.get("Created", ""),
                })
            return result

        return await asyncio.to_thread(_list)

    async def force_remove_containers(self, container_ids: list[str]) -> list[str]:
        """Force remove containers by ID. Returns list of removed IDs."""
        def _remove():
            client = self._get_client()
            removed = []
            for cid in container_ids:
                try:
                    container = client.containers.get(cid)
                    container.remove(force=True)
                    removed.append(cid)
                except Exception as e:
                    logger.warning("force_remove_failed", id=cid[:12], error=str(e))
            return removed

        return await asyncio.to_thread(_remove)

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None


def _parse_memory_bytes(mem_str: str) -> int:
    """Convert '512m' or '2g' to bytes."""
    mem_str = mem_str.strip().lower()
    if mem_str.endswith("g"):
        return int(float(mem_str[:-1]) * 1024 * 1024 * 1024)
    if mem_str.endswith("m"):
        return int(float(mem_str[:-1]) * 1024 * 1024)
    return int(mem_str)
