"""Tests for the Redis plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestRedisPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("redis")

    def test_generate_credentials(self):
        """Redis credentials contain only a password."""
        plugin = get_plugin("redis")
        creds = plugin.generate_credentials({})
        assert "password" in creds
        assert len(creds["password"]) > 20

    def test_get_env_vars(self):
        """Env vars include Redis URL and Celery conventions."""
        plugin = get_plugin("redis")
        creds = {"password": "test_pass"}
        env = plugin.get_env_vars("my-redis", "abc.sandbox.local", creds, {})

        assert env["REDIS_HOST"] == "my-redis.abc.sandbox.local"
        assert env["REDIS_PORT"] == "6379"
        assert "test_pass" in env["REDIS_URL"]
        assert env["CELERY_BROKER_URL"] == env["REDIS_URL"]

    def test_get_docker_config(self):
        """Docker config uses alpine image with requirepass."""
        plugin = get_plugin("redis")
        creds = {"password": "p"}
        cfg = plugin.get_docker_config("my-redis", "sb123", "abc.sandbox.local", creds, {}, "7")

        assert cfg["image"] == "redis:7-alpine"
        assert "--requirepass" in cfg["command"]
        assert "p" in cfg["command"]

    def test_get_agent_tools(self):
        """Redis provides 13 tools."""
        plugin = get_plugin("redis")
        creds = {"password": "p"}
        tools = plugin.get_agent_tools("my-redis", "abc.sandbox.local", creds, {})

        assert len(tools) == 13
        tool_names = {t.name for t in tools}
        assert "redis_get" in tool_names
        assert "redis_set" in tool_names
        assert "redis_flushdb" in tool_names

    def test_no_init_commands(self):
        plugin = get_plugin("redis")
        assert plugin.get_init_commands("r", {"password": "p"}, {}) == []
