"""Tests for the PostgreSQL plugin."""

import pytest

from pysandbox.plugin.registry import clear_registry, get_plugin, is_registered


class TestPostgresPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        """Ensure plugins are loaded."""
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        """Plugin is discovered and registered."""
        assert is_registered("postgres")

    def test_generate_credentials(self):
        """Credentials include user, password, database."""
        plugin = get_plugin("postgres")
        creds = plugin.generate_credentials({"db": "testdb"})

        assert "user" in creds
        assert "password" in creds
        assert creds["database"] == "testdb"
        assert creds["user"].startswith("pysb_")
        assert len(creds["password"]) > 20

    def test_generate_credentials_default_db(self):
        """Default database is sandbox_db."""
        plugin = get_plugin("postgres")
        creds = plugin.generate_credentials({})
        assert creds["database"] == "sandbox_db"

    def test_get_env_vars(self):
        """Env vars include connection URL and components."""
        plugin = get_plugin("postgres")
        creds = {"user": "test_user", "password": "test_pass", "database": "test_db"}
        env = plugin.get_env_vars("my-pg", "abc.sandbox.local", creds, {})

        assert "POSTGRES_URL" in env
        assert "POSTGRES_HOST" in env
        assert env["POSTGRES_HOST"] == "my-pg.abc.sandbox.local"
        assert env["POSTGRES_PORT"] == "5432"
        assert "test_user" in env["POSTGRES_URL"]
        assert "test_pass" in env["POSTGRES_URL"]
        assert env["DATABASE_URL"] == env["POSTGRES_URL"]

    def test_get_docker_config(self):
        """Docker config includes image, env, volumes, healthcheck."""
        plugin = get_plugin("postgres")
        creds = {"user": "u", "password": "p", "database": "d"}
        cfg = plugin.get_docker_config("my-pg", "sandbox-123", "abc.sandbox.local", creds, {}, "16")

        assert cfg["image"] == "postgres:16"
        assert cfg["environment"]["POSTGRES_DB"] == "d"
        assert cfg["environment"]["POSTGRES_USER"] == "u"
        assert "healthcheck" in cfg
        assert "volumes" in cfg

    def test_get_agent_tools(self):
        """Plugin provides SQL tools."""
        plugin = get_plugin("postgres")
        creds = {"user": "u", "password": "p", "database": "d"}
        tools = plugin.get_agent_tools("my-pg", "abc.sandbox.local", creds, {})

        assert len(tools) == 8
        tool_names = {t.name for t in tools}
        assert "sql_query" in tool_names
        assert "sql_execute" in tool_names
        assert "db_list_tables" in tool_names

    def test_get_init_commands(self):
        """Init commands create extensions."""
        plugin = get_plugin("postgres")
        creds = {"user": "u", "password": "p", "database": "d"}
        cmds = plugin.get_init_commands("my-pg", creds, {})

        assert len(cmds) == 2  # uuid-ossp and pgcrypto
        assert "uuid-ossp" in cmds[0]

    def test_custom_extensions(self):
        """Custom extensions are included in init commands."""
        plugin = get_plugin("postgres")
        creds = {"user": "u", "password": "p", "database": "d"}
        cmds = plugin.get_init_commands("my-pg", creds, {"extensions": ["postgis"]})

        assert len(cmds) == 1
        assert "postgis" in cmds[0]
