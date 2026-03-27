"""Tests for the Dremio plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestDremioPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("dremio")

    def test_generate_credentials(self):
        plugin = get_plugin("dremio")
        creds = plugin.generate_credentials({})
        assert creds["user"] == "dremio"
        assert len(creds["password"]) > 10

    def test_generate_credentials_custom(self):
        plugin = get_plugin("dremio")
        creds = plugin.generate_credentials({"admin_user": "admin", "admin_password": "secret123"})
        assert creds["user"] == "admin"
        assert creds["password"] == "secret123"

    def test_get_env_vars(self):
        plugin = get_plugin("dremio")
        creds = {"user": "dremio", "password": "test_pass"}
        env = plugin.get_env_vars("my-dremio", "abc.sandbox.local", creds, {})

        assert env["DREMIO_HOST"] == "my-dremio.abc.sandbox.local"
        assert env["DREMIO_PORT"] == "9047"
        assert env["DREMIO_ODBC_PORT"] == "31010"
        assert env["DREMIO_FLIGHT_PORT"] == "45678"
        assert "DREMIO_URL" in env
        assert "DREMIO_JDBC_URL" in env
        assert "DREMIO_ARROW_FLIGHT_URI" in env

    def test_get_docker_config(self):
        plugin = get_plugin("dremio")
        creds = {"user": "dremio", "password": "p"}
        cfg = plugin.get_docker_config("dremio", "sb123", "abc.sandbox.local", creds, {}, "latest")

        assert cfg["image"] == "dremio/dremio-oss:latest"
        assert "healthcheck" in cfg
        assert "volumes" in cfg

    def test_get_agent_tools(self):
        plugin = get_plugin("dremio")
        creds = {"user": "dremio", "password": "p"}
        tools = plugin.get_agent_tools("dremio", "abc.sandbox.local", creds, {})

        assert len(tools) == 6
        names = {t.name for t in tools}
        assert "dremio_sql" in names
        assert "dremio_list_sources" in names
        assert "dremio_add_source" in names
        assert "dremio_create_space" in names

    def test_init_commands_bootstrap(self):
        plugin = get_plugin("dremio")
        creds = {"user": "dremio", "password": "testpass"}
        cmds = plugin.get_init_commands("dremio", creds, {})

        assert len(cmds) == 1
        assert "firstuser" in cmds[0]
        assert "dremio" in cmds[0]
