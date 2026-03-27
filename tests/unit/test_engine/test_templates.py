"""Tests for Sandbox Templates feature."""

import pytest

from pysandbox.engine.templates import (
    BUILTIN_TEMPLATES,
    SandboxTemplate,
    TemplateRegistry,
)


class TestBuiltinTemplates:
    def test_has_builtin_templates(self):
        assert len(BUILTIN_TEMPLATES) >= 5

    def test_data_lakehouse_template(self):
        t = BUILTIN_TEMPLATES["data-lakehouse"]
        assert t.name == "Data Lakehouse"
        assert t.category == "data"
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "minio" in plugin_ids
        assert "nessie" in plugin_ids
        assert "spark" in plugin_ids
        assert "dremio" in plugin_ids

    def test_ml_pipeline_template(self):
        t = BUILTIN_TEMPLATES["ml-pipeline"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "postgres" in plugin_ids
        assert "jupyter" in plugin_ids

    def test_microservices_template(self):
        t = BUILTIN_TEMPLATES["microservices"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "kafka" in plugin_ids
        assert "redis" in plugin_ids
        assert "prometheus" in plugin_ids

    def test_observability_template(self):
        t = BUILTIN_TEMPLATES["observability"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "prometheus" in plugin_ids
        assert "grafana" in plugin_ids
        assert "jaeger" in plugin_ids

    def test_event_driven_template(self):
        t = BUILTIN_TEMPLATES["event-driven"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "kafka" in plugin_ids
        assert "rabbitmq" in plugin_ids

    def test_graph_analytics_template(self):
        t = BUILTIN_TEMPLATES["graph-analytics"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "neo4j" in plugin_ids

    def test_search_analytics_template(self):
        t = BUILTIN_TEMPLATES["search-analytics"]
        plugin_ids = [p["plugin_id"] for p in t.plugins]
        assert "elasticsearch" in plugin_ids
        assert "clickhouse" in plugin_ids

    def test_all_templates_have_required_fields(self):
        for tid, t in BUILTIN_TEMPLATES.items():
            assert t.id == tid
            assert t.name
            assert t.description
            assert t.category
            assert t.icon
            assert len(t.plugins) >= 2
            assert t.estimated_startup_seconds > 0

    def test_all_plugins_have_startup_order(self):
        for t in BUILTIN_TEMPLATES.values():
            for p in t.plugins:
                assert "startup_order" in p


class TestTemplateRegistry:
    def test_list_all_includes_builtins(self):
        reg = TemplateRegistry()
        all_templates = reg.list_all()
        ids = {t.id for t in all_templates}
        assert "data-lakehouse" in ids
        assert "microservices" in ids

    def test_get_builtin(self):
        reg = TemplateRegistry()
        t = reg.get("data-lakehouse")
        assert t is not None
        assert t.id == "data-lakehouse"

    def test_get_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.get("nonexistent") is None

    def test_register_custom(self):
        reg = TemplateRegistry()
        custom = SandboxTemplate(
            id="custom-test",
            name="Custom Test",
            description="A test template",
            category="test",
            icon="🧪",
            plugins=[
                {"plugin_id": "redis", "name": "redis", "expose": True},
                {"plugin_id": "postgres", "name": "postgres", "expose": True},
            ],
        )
        reg.register(custom)
        assert reg.get("custom-test") is not None
        assert "custom-test" in {t.id for t in reg.list_all()}

    def test_unregister_custom(self):
        reg = TemplateRegistry()
        custom = SandboxTemplate(
            id="to-remove",
            name="Remove Me",
            description="Will be removed",
            category="test",
            icon="🗑️",
            plugins=[{"plugin_id": "redis", "name": "redis", "expose": True},
                     {"plugin_id": "postgres", "name": "pg", "expose": True}],
        )
        reg.register(custom)
        assert reg.unregister("to-remove") is True
        assert reg.get("to-remove") is None

    def test_unregister_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.unregister("nonexistent") is False

    def test_list_all_sorted_by_name(self):
        reg = TemplateRegistry()
        all_templates = reg.list_all()
        names = [t.name for t in all_templates]
        assert names == sorted(names)
