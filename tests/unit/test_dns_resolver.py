"""Tests for DNS resolution."""

import pytest

from pysandbox.runtime.dns_server import SandboxDNSManager, SandboxDNSResolver


class TestSandboxDNSResolver:
    def test_register_and_resolve(self):
        """Registered names resolve to their IPs."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("postgres", "172.20.0.3")

        ip = resolver.resolve("postgres.abc12345.sandbox.local")
        assert ip == "172.20.0.3"

    def test_resolve_unknown_returns_none(self):
        """Unknown names return None."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        assert resolver.resolve("unknown.abc12345.sandbox.local") is None

    def test_resolve_wrong_zone_returns_none(self):
        """Names in wrong zone return None."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("postgres", "172.20.0.3")

        assert resolver.resolve("postgres.different.sandbox.local") is None

    def test_deregister(self):
        """Deregistered names no longer resolve."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("redis", "172.20.0.4")
        resolver.deregister("redis")

        assert resolver.resolve("redis.abc12345.sandbox.local") is None

    def test_case_insensitive(self):
        """DNS resolution is case-insensitive."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("Postgres", "172.20.0.3")

        assert resolver.resolve("postgres.abc12345.sandbox.local") == "172.20.0.3"
        assert resolver.resolve("POSTGRES.ABC12345.SANDBOX.LOCAL") == "172.20.0.3"

    def test_trailing_dot(self):
        """Trailing dots are handled."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("kafka", "172.20.0.5")

        assert resolver.resolve("kafka.abc12345.sandbox.local.") == "172.20.0.5"

    def test_list_records(self):
        """All registered records are listed."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("postgres", "172.20.0.3")
        resolver.register("redis", "172.20.0.4")

        records = resolver.list_records()
        assert records == {"postgres": "172.20.0.3", "redis": "172.20.0.4"}

    def test_multiple_registrations(self):
        """Multiple services resolve independently."""
        resolver = SandboxDNSResolver(zone="abc12345.sandbox.local")
        resolver.register("postgres", "172.20.0.3")
        resolver.register("redis", "172.20.0.4")
        resolver.register("kafka", "172.20.0.5")

        assert resolver.resolve("postgres.abc12345.sandbox.local") == "172.20.0.3"
        assert resolver.resolve("redis.abc12345.sandbox.local") == "172.20.0.4"
        assert resolver.resolve("kafka.abc12345.sandbox.local") == "172.20.0.5"


class TestSandboxDNSManager:
    @pytest.mark.asyncio
    async def test_start_register_resolve(self, dns_manager):
        """Full lifecycle: start, register, resolve, stop."""
        await dns_manager.start_for_sandbox("sb1", "abc12345.sandbox.local", 5300)
        await dns_manager.register("sb1", "postgres", "172.20.0.3")

        ip = await dns_manager.resolve("sb1", "postgres.abc12345.sandbox.local")
        assert ip == "172.20.0.3"

        await dns_manager.stop_for_sandbox("sb1")

    @pytest.mark.asyncio
    async def test_sandboxes_isolated(self, dns_manager):
        """Different sandboxes don't share DNS records."""
        await dns_manager.start_for_sandbox("sb1", "aaa.sandbox.local", 5300)
        await dns_manager.start_for_sandbox("sb2", "bbb.sandbox.local", 5301)

        await dns_manager.register("sb1", "postgres", "172.20.0.3")
        await dns_manager.register("sb2", "postgres", "172.21.0.3")

        ip1 = await dns_manager.resolve("sb1", "postgres.aaa.sandbox.local")
        ip2 = await dns_manager.resolve("sb2", "postgres.bbb.sandbox.local")

        assert ip1 == "172.20.0.3"
        assert ip2 == "172.21.0.3"

        # Cross-sandbox should not resolve
        cross = await dns_manager.resolve("sb1", "postgres.bbb.sandbox.local")
        assert cross is None

        await dns_manager.stop_for_sandbox("sb1")
        await dns_manager.stop_for_sandbox("sb2")

    @pytest.mark.asyncio
    async def test_deregister(self, dns_manager):
        """Deregistered names stop resolving."""
        await dns_manager.start_for_sandbox("sb1", "abc.sandbox.local", 5300)
        await dns_manager.register("sb1", "redis", "172.20.0.4")
        await dns_manager.deregister("sb1", "redis")

        ip = await dns_manager.resolve("sb1", "redis.abc.sandbox.local")
        assert ip is None

        await dns_manager.stop_for_sandbox("sb1")
