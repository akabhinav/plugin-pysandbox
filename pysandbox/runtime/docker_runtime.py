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
        """Create a Docker bridge network. Auto-prunes orphaned networks on pool exhaustion."""
        def _create():
            client = self._get_client()
            network = client.networks.create(
                name=name,
                driver="bridge",
                labels=labels or {},
                check_duplicate=True,
            )
            return network.id

        def _prune_and_create():
            """Prune orphaned pysandbox networks and retry create."""
            client = self._get_client()
            pruned = 0
            networks = client.networks.list(filters={"label": "pysandbox.sandbox_id"})
            for n in networks:
                try:
                    if n.name == name:
                        continue  # Don't prune the network we're trying to create
                    n.reload()
                    containers = n.attrs.get("Containers", {})
                    if not containers:
                        n.remove()
                        pruned += 1
                except Exception:
                    pass
            logger.info("auto_pruned_networks", count=pruned)
            # Retry create
            network = client.networks.create(
                name=name,
                driver="bridge",
                labels=labels or {},
                check_duplicate=True,
            )
            return network.id

        try:
            network_id = await asyncio.to_thread(_create)
        except Exception as e:
            if "address pools" in str(e).lower() or "subnetted" in str(e).lower():
                logger.warning("network_pool_exhausted_auto_pruning")
                network_id = await asyncio.to_thread(_prune_and_create)
            else:
                raise

        logger.info("docker_network_created", name=name, id=network_id[:12])
        return network_id

    async def remove_network(self, name: str) -> None:
        """Remove a Docker network by name. Force-disconnects any remaining containers."""
        def _remove():
            client = self._get_client()
            try:
                network = client.networks.get(name)
                network.reload()
                # Force disconnect any remaining containers
                for cid in list(network.attrs.get("Containers", {}).keys()):
                    try:
                        network.disconnect(cid, force=True)
                    except Exception:
                        pass
                network.remove()
                logger.info("network_removed", name=name)
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
        port_mappings: dict[int, int] | None = None,
    ) -> str:
        """Create and start a container. Returns container ID."""
        def _create():
            client = self._get_client()

            # Build port bindings — use port_mappings if provided, else single port
            ports = {}
            if port_mappings:
                for cport, hport in port_mappings.items():
                    ports[f"{cport}/tcp"] = hport
            elif host_port and container_port:
                ports[f"{container_port}/tcp"] = host_port

            # Extract config
            image = docker_config.get("image", "")
            environment = docker_config.get("environment", {})
            volumes = docker_config.get("volumes", {})
            command = docker_config.get("command")
            healthcheck = docker_config.get("healthcheck")

            # Parse memory limit
            mem_bytes = _parse_memory_bytes(memory_limit)

            # Pull image first (can be slow), before touching the network
            try:
                client.images.get(image)
            except Exception:
                logger.info("pulling_image", image=image)
                client.images.pull(image)

            # Verify network still exists before creating container
            try:
                client.networks.get(network)
            except Exception as e:
                raise RuntimeError(
                    f"Network '{network}' not found before container create. "
                    f"It may have been removed by a concurrent operation."
                ) from e

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

    async def get_container_stats(self, container_id: str) -> dict:
        """Get live resource usage stats for a container."""
        def _stats():
            client = self._get_client()
            try:
                container = client.containers.get(container_id)
                raw = container.stats(stream=False)

                # Calculate CPU percentage
                cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - \
                    raw["precpu_stats"]["cpu_usage"]["total_usage"]
                system_delta = raw["cpu_stats"]["system_cpu_usage"] - \
                    raw["precpu_stats"]["system_cpu_usage"]
                num_cpus = raw["cpu_stats"].get("online_cpus", 1)
                cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0 if system_delta > 0 else 0.0

                # Memory usage
                mem_usage = raw["memory_stats"].get("usage", 0)
                mem_limit = raw["memory_stats"].get("limit", 0)
                mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0

                # Network I/O
                net_rx = 0
                net_tx = 0
                for iface in raw.get("networks", {}).values():
                    net_rx += iface.get("rx_bytes", 0)
                    net_tx += iface.get("tx_bytes", 0)

                return {
                    "container_id": container_id[:12],
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_usage_mb": round(mem_usage / 1024 / 1024, 1),
                    "memory_limit_mb": round(mem_limit / 1024 / 1024, 1),
                    "memory_percent": round(mem_percent, 2),
                    "network_rx_mb": round(net_rx / 1024 / 1024, 2),
                    "network_tx_mb": round(net_tx / 1024 / 1024, 2),
                }
            except Exception as e:
                return {
                    "container_id": container_id[:12],
                    "error": str(e),
                    "cpu_percent": 0,
                    "memory_usage_mb": 0,
                    "memory_limit_mb": 0,
                    "memory_percent": 0,
                    "network_rx_mb": 0,
                    "network_tx_mb": 0,
                }

        return await asyncio.to_thread(_stats)

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
                host_ports = {}
                for port_key, port_info in ports.items():
                    if port_info:
                        hp = port_info[0].get("HostPort")
                        if hp:
                            # Extract container port number from "9000/tcp"
                            cport = port_key.split("/")[0]
                            host_ports[cport] = hp
                            if host_port is None:
                                host_port = hp
                result.append({
                    "id": c.id,
                    "short_id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:20],
                    "status": c.status,
                    "host_port": host_port,
                    "host_ports": host_ports,
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

    async def list_managed_networks(self) -> list[dict]:
        """List all pysandbox-managed Docker networks."""
        def _list():
            client = self._get_client()
            networks = client.networks.list(filters={"label": "pysandbox.sandbox_id"})
            result = []
            for n in networks:
                n.reload()
                containers = n.attrs.get("Containers", {})
                result.append({
                    "id": n.id,
                    "short_id": n.short_id,
                    "name": n.name,
                    "sandbox_id": n.attrs.get("Labels", {}).get("pysandbox.sandbox_id", ""),
                    "containers": len(containers),
                    "created": n.attrs.get("Created", ""),
                })
            return result

        return await asyncio.to_thread(_list)

    async def prune_managed_networks(self, active_network_names: set[str] | None = None) -> list[str]:
        """Remove pysandbox networks that have no running containers.

        Networks listed in *active_network_names* are never pruned,
        even if they are momentarily empty (e.g. between plugin installs).
        """
        active = active_network_names or set()

        def _prune():
            client = self._get_client()
            networks = client.networks.list(filters={"label": "pysandbox.sandbox_id"})
            removed = []
            for n in networks:
                try:
                    if n.name in active:
                        continue  # Skip networks belonging to active sandboxes
                    n.reload()
                    containers = n.attrs.get("Containers", {})
                    if not containers:
                        name = n.name
                        n.remove()
                        removed.append(name)
                        logger.info("network_pruned", name=name)
                except Exception as e:
                    logger.warning("network_prune_failed", name=n.name, error=str(e))
            return removed

        return await asyncio.to_thread(_prune)

    async def force_remove_networks(self, network_ids: list[str]) -> list[str]:
        """Force disconnect all containers and remove networks. Returns removed names."""
        def _remove():
            client = self._get_client()
            removed = []
            for nid in network_ids:
                try:
                    network = client.networks.get(nid)
                    # Disconnect all containers first
                    network.reload()
                    for cid in list(network.attrs.get("Containers", {}).keys()):
                        try:
                            network.disconnect(cid, force=True)
                        except Exception:
                            pass
                    name = network.name
                    network.remove()
                    removed.append(name)
                except Exception as e:
                    logger.warning("network_force_remove_failed", id=nid[:12], error=str(e))
            return removed

        return await asyncio.to_thread(_remove)

    async def full_cleanup(self) -> dict:
        """Remove ALL pysandbox containers and networks. Returns summary."""
        def _cleanup():
            client = self._get_client()
            result = {"containers_removed": 0, "networks_removed": 0}

            # Remove all managed containers
            containers = client.containers.list(
                all=True, filters={"label": "pysandbox.managed=true"},
            )
            for c in containers:
                try:
                    c.remove(force=True)
                    result["containers_removed"] += 1
                except Exception:
                    pass

            # Remove all managed networks
            networks = client.networks.list(filters={"label": "pysandbox.sandbox_id"})
            for n in networks:
                try:
                    n.reload()
                    for cid in list(n.attrs.get("Containers", {}).keys()):
                        try:
                            n.disconnect(cid, force=True)
                        except Exception:
                            pass
                    n.remove()
                    result["networks_removed"] += 1
                except Exception:
                    pass

            return result

        return await asyncio.to_thread(_cleanup)

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
