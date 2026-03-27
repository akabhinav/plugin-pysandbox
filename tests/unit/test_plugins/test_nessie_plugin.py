"""Tests for the Nessie plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestNessiePlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("nessie")

    def test_generate_credentials_empty(self):
        plugin = get_plugin("nessie")
        creds = plugin.generate_credentials({})
        assert creds == {}

    def test_get_env_vars(self):
        plugin = get_plugin("nessie")
        env = plugin.get_env_vars("nessie", "abc.sandbox.local", {}, {})

        assert env["NESSIE_HOST"] == "nessie.abc.sandbox.local"
        assert env["NESSIE_PORT"] == "19120"
        assert "NESSIE_URI" in env
        assert "NESSIE_CATALOG_URI" in env
        assert "/api/v2" in env["NESSIE_URI"]

    def test_get_docker_config(self):
        plugin = get_plugin("nessie")
        cfg = plugin.get_docker_config("nessie", "sb123", "abc.sandbox.local", {}, {}, "latest")

        assert cfg["image"] == "ghcr.io/projectnessie/nessie:latest"
        assert "healthcheck" in cfg
        assert cfg["environment"]["NESSIE_VERSION_STORE_TYPE"] == "IN_MEMORY"

    def test_get_agent_tools(self):
        plugin = get_plugin("nessie")
        tools = plugin.get_agent_tools("nessie", "abc.sandbox.local", {}, {})

        assert len(tools) == 7
        names = {t.name for t in tools}
        assert "nessie_list_branches" in names
        assert "nessie_create_branch" in names
        assert "nessie_merge" in names
        assert "nessie_list_contents" in names
        assert "nessie_commit_log" in names
        assert "nessie_create_tag" in names

    def test_init_commands_empty(self):
        plugin = get_plugin("nessie")
        cmds = plugin.get_init_commands("nessie", {}, {})
        assert cmds == []
