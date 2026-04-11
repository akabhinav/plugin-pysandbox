"""Tests for the ephemeral sandbox launcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pysandbox.engine.ephemeral import (
    EphemeralSandboxLauncher,
    _gen_short_id,
    parse_ephemeral_request,
    resolve_stack,
)


class TestResolveStack:
    def test_preset_returns_plugin_list(self):
        assert resolve_stack("microservices", None) == ["postgres", "redis", "kafka"]

    def test_plus_delimited_list(self):
        assert resolve_stack("postgres+redis", None) == ["postgres", "redis"]

    def test_comma_delimited_list(self):
        assert resolve_stack("postgres,redis,kafka", None) == ["postgres", "redis", "kafka"]

    def test_explicit_plugins_win_over_stack(self):
        assert resolve_stack("microservices", ["mongodb"]) == ["mongodb"]

    def test_empty_input_returns_empty(self):
        assert resolve_stack(None, None) == []

    def test_whitespace_trimmed(self):
        assert resolve_stack(" postgres + redis ", None) == ["postgres", "redis"]


class TestParseRequest:
    def test_ttl_default_applied(self):
        spec = parse_ephemeral_request(stack="web")
        assert spec.ttl_seconds == 1800

    def test_ttl_clamped_to_max(self):
        spec = parse_ephemeral_request(stack="web", ttl_seconds=10_000, max_ttl_seconds=3600)
        assert spec.ttl_seconds == 3600

    def test_ttl_clamped_to_min(self):
        spec = parse_ephemeral_request(stack="web", ttl_seconds=5)
        assert spec.ttl_seconds == 60

    def test_no_plugins_raises(self):
        with pytest.raises(ValueError, match="No plugins"):
            parse_ephemeral_request()

    def test_preset_stack_resolved(self):
        spec = parse_ephemeral_request(stack="web")
        assert "postgres" in spec.plugins
        assert "redis" in spec.plugins

    def test_name_passed_through(self):
        spec = parse_ephemeral_request(stack="web", name="bug-repro")
        assert spec.name == "bug-repro"


class TestShortId:
    def test_short_id_length(self):
        sid = _gen_short_id(6)
        assert len(sid) == 6

    def test_short_id_uses_unambiguous_alphabet(self):
        sid = _gen_short_id(100)
        for ch in sid:
            assert ch not in "0O1IlL"

    def test_short_id_changes(self):
        seen = {_gen_short_id() for _ in range(50)}
        # Not guaranteed but collision probability is vanishingly small.
        assert len(seen) > 45


class TestLauncher:
    @pytest.fixture
    def sandbox_engine(self):
        engine = MagicMock()
        engine.create = AsyncMock(return_value={
            "id": "sb-123",
            "name": "eph-x7k9m2",
            "status": "running",
            "dns_zone": "sb-123.sandbox.local",
        })
        return engine

    @pytest.fixture
    def ttl_manager(self):
        mgr = MagicMock()
        mgr.set_ttl = MagicMock(return_value={
            "ttl_seconds": 1800,
            "expires_at": "2026-01-01T13:00:00+00:00",
        })
        return mgr

    @pytest.mark.asyncio
    async def test_launch_creates_sandbox_and_sets_ttl(
        self, sandbox_engine, ttl_manager,
    ):
        launcher = EphemeralSandboxLauncher(sandbox_engine, ttl_manager)
        result = await launcher.launch_from_request(stack="web", ttl_seconds=1800)
        sandbox_engine.create.assert_awaited_once()
        call_kwargs = sandbox_engine.create.call_args.kwargs
        assert call_kwargs["owner_id"] == "ephemeral"
        assert call_kwargs["tags"]["ephemeral"] == "true"
        assert [p["plugin_id"] for p in call_kwargs["plugins"]] == ["postgres", "redis"]
        ttl_manager.set_ttl.assert_called_once_with("sb-123", 1800)
        assert "short_id" in result
        assert result["sandbox_id"] == "sb-123"

    @pytest.mark.asyncio
    async def test_launch_auto_names_when_no_name(self, sandbox_engine, ttl_manager):
        launcher = EphemeralSandboxLauncher(sandbox_engine, ttl_manager)
        await launcher.launch_from_request(stack="web")
        call_kwargs = sandbox_engine.create.call_args.kwargs
        assert call_kwargs["name"].startswith("eph-")

    @pytest.mark.asyncio
    async def test_short_ids_are_unique(self, sandbox_engine, ttl_manager):
        launcher = EphemeralSandboxLauncher(sandbox_engine, ttl_manager)
        r1 = await launcher.launch_from_request(stack="web")
        r2 = await launcher.launch_from_request(stack="web")
        assert r1["short_id"] != r2["short_id"]

    @pytest.mark.asyncio
    async def test_explicit_plugins_passthrough(self, sandbox_engine, ttl_manager):
        launcher = EphemeralSandboxLauncher(sandbox_engine, ttl_manager)
        await launcher.launch_from_request(plugins=["mongodb"])
        call_kwargs = sandbox_engine.create.call_args.kwargs
        assert [p["plugin_id"] for p in call_kwargs["plugins"]] == ["mongodb"]

    @pytest.mark.asyncio
    async def test_invalid_request_raises(self, sandbox_engine, ttl_manager):
        launcher = EphemeralSandboxLauncher(sandbox_engine, ttl_manager)
        with pytest.raises(ValueError):
            await launcher.launch_from_request()

    def test_release_short_id_allows_reuse(self, sandbox_engine, ttl_manager):
        registry: set[str] = set()
        launcher = EphemeralSandboxLauncher(
            sandbox_engine, ttl_manager, short_id_registry=registry,
        )
        sid = launcher._allocate_short_id()
        assert sid in registry
        launcher.release_short_id(sid)
        assert sid not in registry
