"""Tests for the Timeline API endpoints."""

import pytest
from fastapi.testclient import TestClient

from pysandbox.engine.activity_timeline import ActivityTimeline


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.timeline import router
    app = FastAPI()
    app.include_router(router)
    tl = ActivityTimeline()
    tl.record("sb1", "plugin.installed", "Installed postgres", plugin_name="postgres")
    tl.record("sb1", "plugin.installed", "Installed redis", plugin_name="redis")
    app.state.activity_timeline = tl
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTimelineAPI:
    def test_get_timeline(self, client):
        resp = client.get("/v1/timeline/sb1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["entries"]) == 2

    def test_get_timeline_limit(self, client):
        resp = client.get("/v1/timeline/sb1?limit=1")
        data = resp.json()
        assert len(data["entries"]) == 1

    def test_get_timeline_empty(self, client):
        resp = client.get("/v1/timeline/sb999")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_add_entry(self, client):
        resp = client.post("/v1/timeline/sb1", json={
            "event_type": "user.note",
            "description": "Manual note",
            "severity": "info",
        })
        assert resp.status_code == 200
        assert resp.json()["entry"]["description"] == "Manual note"

    def test_clear_timeline(self, client):
        resp = client.delete("/v1/timeline/sb1")
        assert resp.status_code == 200

        resp2 = client.get("/v1/timeline/sb1")
        assert resp2.json()["total"] == 0

    def test_filter_by_event_type(self, client):
        resp = client.get("/v1/timeline/sb1?event_type=plugin.installed")
        data = resp.json()
        assert len(data["entries"]) == 2
