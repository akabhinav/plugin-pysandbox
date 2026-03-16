"""Per-sandbox DNS server — resolves {name}.{zone} to container IPs."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


class SandboxDNSResolver:
    """Holds name→IP mapping for a single sandbox. Thread-safe via GIL."""

    def __init__(self, zone: str) -> None:
        self.zone = zone
        self._records: dict[str, str] = {}

    def register(self, name: str, ip: str) -> None:
        self._records[name.lower()] = ip
        logger.info("dns_registered", name=f"{name}.{self.zone}", ip=ip)

    def deregister(self, name: str) -> None:
        self._records.pop(name.lower(), None)
        logger.info("dns_deregistered", name=f"{name}.{self.zone}")

    def resolve(self, qname: str) -> str | None:
        """Resolve a fully-qualified name. Returns IP or None."""
        qname = qname.rstrip(".").lower()
        suffix = f".{self.zone}"
        if qname.endswith(suffix):
            label = qname[: -len(suffix)]
            return self._records.get(label)
        return None

    def list_records(self) -> dict[str, str]:
        return dict(self._records)


class SandboxDNSManager:
    """Manages per-sandbox DNS resolvers. Full DNS server is optional."""

    def __init__(self) -> None:
        self._resolvers: dict[str, SandboxDNSResolver] = {}

    async def start_for_sandbox(self, sandbox_id: str, dns_zone: str, dns_port: int) -> None:
        """Create a resolver for a sandbox. DNS server start is optional."""
        resolver = SandboxDNSResolver(zone=dns_zone)
        self._resolvers[sandbox_id] = resolver
        logger.info("dns_started", sandbox_id=sandbox_id, zone=dns_zone, port=dns_port)

    async def register(self, sandbox_id: str, name: str, ip: str) -> None:
        resolver = self._resolvers.get(sandbox_id)
        if resolver:
            resolver.register(name, ip)

    async def deregister(self, sandbox_id: str, name: str) -> None:
        resolver = self._resolvers.get(sandbox_id)
        if resolver:
            resolver.deregister(name)

    async def resolve(self, sandbox_id: str, qname: str) -> str | None:
        resolver = self._resolvers.get(sandbox_id)
        if resolver:
            return resolver.resolve(qname)
        return None

    def get_records(self, sandbox_id: str) -> dict[str, str]:
        resolver = self._resolvers.get(sandbox_id)
        return resolver.list_records() if resolver else {}

    async def stop_for_sandbox(self, sandbox_id: str) -> None:
        self._resolvers.pop(sandbox_id, None)
        logger.info("dns_stopped", sandbox_id=sandbox_id)
