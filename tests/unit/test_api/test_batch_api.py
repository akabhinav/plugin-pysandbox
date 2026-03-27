"""Tests for the Batch Operations API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.batch import router
    app = FastAPI()
    app.include_router(router)

    engine = MagicMock()
    engine.pause = AsyncMock()
    engine.resume = AsyncMock()
    engine.destroy = AsyncMock()
    engine.get = AsyncMock(return_value={
        "id": "sb1", "name": "test", "status": "running",
        "docker_network": "pysb-123", "dns_zone": "123.sandbox.local",
    })
    engine._plugins = MagicMock()
    engine._plugins.install = AsyncMock()
    engine._plugins._repo = MagicMock()
    engine._plugins._repo.list_instances = AsyncMock(return_value=[])
    app.state.sandbox_engine = engine
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestBatchAPI:
    def test_batch_pause(self, client):
        resp = client.post("/v1/batch/pause", json={"sandbox_ids": ["sb1", "sb2"]})
        assert resp.status_code == 200
        assert len(resp.json()["succeeded"]) == 2

    def test_batch_resume(self, client):
        resp = client.post("/v1/batch/resume", json={"sandbox_ids": ["sb1"]})
        assert resp.status_code == 200
        assert len(resp.json()["succeeded"]) == 1

    def test_batch_destroy(self, client):
        resp = client.post("/v1/batch/destroy", json={"sandbox_ids": ["sb1", "sb2"]})
        assert resp.status_code == 200
        assert len(resp.json()["succeeded"]) == 2

    def test_batch_pause_with_failure(self, client, app):
        app.state.sandbox_engine.pause = AsyncMock(side_effect=[None, Exception("fail")])
        resp = client.post("/v1/batch/pause", json={"sandbox_ids": ["sb1", "sb2"]})
        data = resp.json()
        assert len(data["succeeded"]) == 1
        assert len(data["failed"]) == 1

    def test_batch_install_plugin(self, client):
        resp = client.post("/v1/batch/install-plugin", json={
            "sandbox_ids": ["sb1"],
            "plugin_id": "redis",
        })
        assert resp.status_code == 200
        assert len(resp.json()["succeeded"]) == 1

    def test_batch_status(self, client):
        resp = client.get("/v1/batch/status?sandbox_ids=sb1,sb2")
        assert resp.status_code == 200
        assert len(resp.json()["sandboxes"]) == 2

    def test_batch_status_empty(self, client):
        resp = client.get("/v1/batch/status")
        assert resp.status_code == 200
        assert resp.json()["sandboxes"] == []
