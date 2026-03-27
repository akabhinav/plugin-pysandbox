"""Tests for Plugin Dependency Auto-Resolution."""

import pytest

from pysandbox.engine.dependency_resolver import DependencyResolver
from pysandbox.plugin.loader import discover_and_load_all


class TestDependencyResolver:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        discover_and_load_all()

    def test_resolve_no_deps(self):
        """Plugins with no dependencies pass through."""
        plugins = [
            {"plugin_id": "redis", "name": "redis", "expose": True},
            {"plugin_id": "postgres", "name": "postgres", "expose": True},
        ]
        result = DependencyResolver.resolve(plugins)
        ids = [p["plugin_id"] for p in result]
        assert "redis" in ids
        assert "postgres" in ids

    def test_resolve_preserves_config(self):
        plugins = [
            {"plugin_id": "redis", "name": "redis", "expose": True, "config": {"maxmemory": "256m"}},
        ]
        result = DependencyResolver.resolve(plugins)
        assert result[0]["config"] == {"maxmemory": "256m"}

    def test_resolve_skips_already_installed(self):
        plugins = [
            {"plugin_id": "redis", "name": "redis", "expose": True},
        ]
        result = DependencyResolver.resolve(plugins, installed_plugin_ids={"redis"})
        assert len(result) == 0

    def test_resolve_assigns_startup_order(self):
        plugins = [
            {"plugin_id": "redis", "name": "redis", "expose": True},
            {"plugin_id": "postgres", "name": "postgres", "expose": True},
        ]
        result = DependencyResolver.resolve(plugins)
        for p in result:
            assert "startup_order" in p

    def test_get_dependency_tree(self):
        tree = DependencyResolver.get_dependency_tree("redis")
        assert tree["plugin_id"] == "redis"
        assert isinstance(tree["dependencies"], list)

    def test_resolve_empty_list(self):
        result = DependencyResolver.resolve([])
        assert result == []

    def test_resolve_deduplicates(self):
        plugins = [
            {"plugin_id": "redis", "name": "redis1", "expose": True},
            {"plugin_id": "redis", "name": "redis2", "expose": True},
        ]
        result = DependencyResolver.resolve(plugins)
        pids = [p["plugin_id"] for p in result]
        assert pids.count("redis") == 1
