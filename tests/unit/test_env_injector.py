"""Tests for environment variable injection."""

import pytest

from pysandbox.runtime.env_injector import EnvInjector


class TestEnvInjector:
    @pytest.mark.asyncio
    async def test_inject_and_get(self, env_injector):
        """Injected vars are retrievable."""
        await env_injector.inject("sb1", {"POSTGRES_URL": "postgresql://...", "REDIS_URL": "redis://..."})

        env = env_injector.get_all("sb1")
        assert env["POSTGRES_URL"] == "postgresql://..."
        assert env["REDIS_URL"] == "redis://..."

    @pytest.mark.asyncio
    async def test_remove_vars(self, env_injector):
        """Removed vars are gone."""
        await env_injector.inject("sb1", {"A": "1", "B": "2", "C": "3"})
        await env_injector.remove("sb1", ["B"])

        env = env_injector.get_all("sb1")
        assert "A" in env
        assert "B" not in env
        assert "C" in env

    @pytest.mark.asyncio
    async def test_sandboxes_isolated(self, env_injector):
        """Different sandboxes have independent environments."""
        await env_injector.inject("sb1", {"KEY": "val1"})
        await env_injector.inject("sb2", {"KEY": "val2"})

        assert env_injector.get_all("sb1")["KEY"] == "val1"
        assert env_injector.get_all("sb2")["KEY"] == "val2"

    @pytest.mark.asyncio
    async def test_redacted_secrets(self, env_injector):
        """Secrets are redacted in get_redacted."""
        await env_injector.inject("sb1", {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PASSWORD": "secret123",
            "AWS_SECRET_ACCESS_KEY": "mykey",
            "API_TOKEN": "tok123",
        })

        redacted = env_injector.get_redacted("sb1")
        assert redacted["POSTGRES_HOST"] == "localhost"
        assert redacted["POSTGRES_PASSWORD"] == "***"
        assert redacted["AWS_SECRET_ACCESS_KEY"] == "***"
        assert redacted["API_TOKEN"] == "***"

    @pytest.mark.asyncio
    async def test_clear_sandbox(self, env_injector):
        """Clearing removes all vars for a sandbox."""
        await env_injector.inject("sb1", {"A": "1"})
        env_injector.clear_sandbox("sb1")
        assert env_injector.get_all("sb1") == {}

    @pytest.mark.asyncio
    async def test_inject_overwrites(self, env_injector):
        """Re-injecting same key overwrites value."""
        await env_injector.inject("sb1", {"KEY": "old"})
        await env_injector.inject("sb1", {"KEY": "new"})
        assert env_injector.get_all("sb1")["KEY"] == "new"

    @pytest.mark.asyncio
    async def test_empty_sandbox(self, env_injector):
        """Getting env for nonexistent sandbox returns empty dict."""
        assert env_injector.get_all("nonexistent") == {}
