"""Tests for port allocation."""

import pytest

from pysandbox.runtime.port_allocator import PortAllocator


class TestPortAllocator:
    def test_allocate_host_port(self, port_allocator):
        """Allocates ports sequentially."""
        p1 = port_allocator.allocate_host_port()
        p2 = port_allocator.allocate_host_port()
        assert p1 == 30000
        assert p2 == 30001

    def test_release_and_reuse(self, port_allocator):
        """Released ports can be reused."""
        p1 = port_allocator.allocate_host_port()
        port_allocator.release_host_port(p1)
        p2 = port_allocator.allocate_host_port()
        assert p2 == p1

    def test_allocate_dns_port(self, port_allocator):
        """DNS ports are allocated from their own range."""
        p = port_allocator.allocate_dns_port()
        assert 6300 <= p <= 6400

    def test_no_duplicates(self, port_allocator):
        """All allocated ports are unique."""
        ports = {port_allocator.allocate_host_port() for _ in range(10)}
        assert len(ports) == 10

    def test_exhaustion_raises(self):
        """Exhausting port range raises RuntimeError."""
        pa = PortAllocator(host_range_start=50000, host_range_end=50002)
        pa.allocate_host_port()
        pa.allocate_host_port()
        pa.allocate_host_port()
        with pytest.raises(RuntimeError):
            pa.allocate_host_port()
