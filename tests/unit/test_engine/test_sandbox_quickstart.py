"""Tests for quickstart guide definitions."""

from pysandbox.engine.sandbox_quickstart import (
    QUICKSTARTS,
    get_quickstart,
    list_quickstarts,
)


class TestQuickstartDefinitions:
    def test_microservices_quickstart_exists(self):
        qs = get_quickstart("microservices")
        assert qs is not None
        assert len(qs.steps) >= 5

    def test_ml_pipeline_quickstart_exists(self):
        qs = get_quickstart("ml-pipeline")
        assert qs is not None
        assert len(qs.steps) >= 3

    def test_event_driven_quickstart_exists(self):
        qs = get_quickstart("event-driven")
        assert qs is not None

    def test_data_lakehouse_quickstart_exists(self):
        qs = get_quickstart("data-lakehouse")
        assert qs is not None

    def test_graph_analytics_quickstart_exists(self):
        qs = get_quickstart("graph-analytics")
        assert qs is not None

    def test_search_analytics_quickstart_exists(self):
        qs = get_quickstart("search-analytics")
        assert qs is not None

    def test_observability_quickstart_exists(self):
        qs = get_quickstart("observability")
        assert qs is not None

    def test_nonexistent_quickstart(self):
        assert get_quickstart("nonexistent") is None

    def test_list_quickstarts(self):
        guides = list_quickstarts()
        assert len(guides) >= 7
        for g in guides:
            assert "template_id" in g
            assert "title" in g
            assert "estimated_minutes" in g
            assert "total_steps" in g

    def test_quickstart_to_dict(self):
        qs = get_quickstart("microservices")
        d = qs.to_dict()
        assert d["template_id"] == "microservices"
        assert d["total_steps"] == len(qs.steps)
        for step in d["steps"]:
            assert "step" in step
            assert "title" in step
            assert "plugin" in step

    def test_all_quickstarts_have_valid_steps(self):
        for template_id, qs in QUICKSTARTS.items():
            assert qs.title, f"No title for {template_id}"
            assert qs.estimated_minutes > 0, f"No estimated time for {template_id}"
            for step in qs.steps:
                assert step.title, f"No title in step for {template_id}"
                assert step.plugin, f"No plugin in step for {template_id}"
                assert step.description, f"No description in step for {template_id}"
