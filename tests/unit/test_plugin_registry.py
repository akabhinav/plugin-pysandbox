"""Tests for plugin registry and auto-discovery."""

import pytest

from pysandbox.plugin.exceptions import PluginNotFoundError
from pysandbox.plugin.registry import (
    clear_registry,
    get_plugin,
    is_registered,
    list_plugin_ids,
    list_plugins,
)


class TestPluginRegistry:
    @pytest.fixture(autouse=True)
    def _load_all(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_discover_loads_plugins(self):
        """Auto-discovery loads all plugin modules."""
        ids = list_plugin_ids()
        assert len(ids) >= 10  # We have 20+ plugins

    def test_all_core_plugins_registered(self):
        """All core plugins are discoverable."""
        expected = [
            "postgres", "redis", "mysql", "mongodb", "elasticsearch",
            "clickhouse", "neo4j", "cassandra", "sqlite",
            "kafka", "rabbitmq", "nats",
            "localstack", "minio", "vault",
            "code-executor", "docker-daemon", "jupyter",
            "prometheus", "grafana", "jaeger",
        ]
        for plugin_id in expected:
            assert is_registered(plugin_id), f"Plugin '{plugin_id}' not registered"

    def test_get_plugin_returns_instance(self):
        """get_plugin returns a fresh plugin instance."""
        plugin = get_plugin("postgres")
        assert plugin is not None
        assert hasattr(plugin, "manifest")
        assert plugin.manifest.id == "postgres"

    def test_get_unknown_plugin_raises(self):
        """Getting an unregistered plugin raises PluginNotFoundError."""
        with pytest.raises(PluginNotFoundError):
            get_plugin("nonexistent-plugin")

    def test_list_plugins_returns_manifests(self):
        """list_plugins returns PluginManifest objects."""
        manifests = list_plugins()
        assert len(manifests) >= 10
        for m in manifests:
            assert m.id
            assert m.display_name
            assert m.category

    def test_each_plugin_has_manifest(self):
        """Every registered plugin has a valid manifest."""
        for plugin_id in list_plugin_ids():
            plugin = get_plugin(plugin_id)
            assert plugin.manifest.id == plugin_id
            assert plugin.manifest.version
            assert plugin.manifest.docker_image

    def test_plugins_implement_interface(self):
        """Every registered plugin implements all required abstract methods."""
        for plugin_id in list_plugin_ids():
            plugin = get_plugin(plugin_id)
            # These should all be callable without raising NotImplementedError
            assert callable(plugin.get_docker_config)
            assert callable(plugin.get_env_vars)
            assert callable(plugin.get_agent_tools)
            assert callable(plugin.generate_credentials)
            assert callable(plugin.get_init_commands)

    def test_credentials_generation(self):
        """Every plugin's generate_credentials returns a dict."""
        for plugin_id in list_plugin_ids():
            plugin = get_plugin(plugin_id)
            creds = plugin.generate_credentials({})
            assert isinstance(creds, dict)

    def test_env_vars_generation(self):
        """Every plugin's get_env_vars returns a dict of strings."""
        for plugin_id in list_plugin_ids():
            plugin = get_plugin(plugin_id)
            creds = plugin.generate_credentials({})
            env = plugin.get_env_vars("test-instance", "abc.sandbox.local", creds, {})
            assert isinstance(env, dict)
            for k, v in env.items():
                assert isinstance(k, str)
                assert isinstance(v, str)
