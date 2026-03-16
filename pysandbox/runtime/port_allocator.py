"""Port allocation for host-exposed plugin ports and DNS servers."""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()


class PortAllocator:
    """Thread-safe port allocator for host ports and DNS ports."""

    def __init__(
        self,
        host_range_start: int = 20000,
        host_range_end: int = 29999,
        dns_range_start: int = 5300,
        dns_range_end: int = 5599,
    ) -> None:
        self._lock = threading.Lock()
        self._host_ports: set[int] = set()
        self._dns_ports: set[int] = set()
        self._host_range = (host_range_start, host_range_end)
        self._dns_range = (dns_range_start, dns_range_end)

    def allocate_host_port(self) -> int:
        """Allocate the next available host port."""
        with self._lock:
            for port in range(self._host_range[0], self._host_range[1] + 1):
                if port not in self._host_ports:
                    self._host_ports.add(port)
                    return port
        raise RuntimeError("No host ports available")

    def release_host_port(self, port: int) -> None:
        with self._lock:
            self._host_ports.discard(port)

    def allocate_dns_port(self) -> int:
        """Allocate the next available DNS port."""
        with self._lock:
            for port in range(self._dns_range[0], self._dns_range[1] + 1):
                if port not in self._dns_ports:
                    self._dns_ports.add(port)
                    return port
        raise RuntimeError("No DNS ports available")

    def release_dns_port(self, port: int) -> None:
        with self._lock:
            self._dns_ports.discard(port)
