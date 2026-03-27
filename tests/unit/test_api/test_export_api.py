"""Tests for the Export/Import API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.export import router
    app = FastAPI()
    app.include_router(router)

    # Mock sandbox engine
    engine = MagicMock()
    engine.get = AsyncMock(return_value={
        "id": "sb1", "name": "test-sb",
        "tags": {}, "total_cpu": 4.0,
        "total_memory_gb": 8.0, "total_disk_gb": 50.0,
    })
    engine._plugins = MagicMock()
    engine._plugins._repo = MagicMock()
    engine._plugins._repo.list_instances = AsyncMock(return_value=[
        {
            "plugin_id": "redis", "plugin_name": "redis",
            "version": "7", "config": {}, "startup_order": 10,
            "host_port": 20001, "host_ports": {6379: 20001},
        },
    ])
    engine.create = AsyncMock(return_value={"id": "sb2", "name": "imported"})
    app.state.sandbox_engine = engine
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestExportAPI:
    def test_export_sandbox(self, client):
        resp = client.get("/v1/export/sb1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert data["sandbox"]["name"] == "test-sb"
        assert len(data["plugins"]) == 1

    def test_export_not_found(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value=None)
        resp = client.get("/v1/export/sb999")
        assert resp.status_code == 404

    def test_import_sandbox(self, client):
        resp = client.post("/v1/export/import", json={
            "config": {
                "sandbox": {"name": "test"},
                "plugins": [{"plugin_id": "redis"}],
            },
            "name_override": "my-import",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_plugins"] == 1

    def test_import_invalid(self, client):
        resp = client.post("/v1/export/import", json={
            "config": {"no_sandbox": True},
        })
        assert resp.status_code == 400

    def test_validate_valid(self, client):
        resp = client.post("/v1/export/validate", json={
            "sandbox": {"name": "test"},
            "plugins": [{"plugin_id": "redis"}],
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_invalid(self, client):
        resp = client.post("/v1/export/validate", json={
            "just_random": True,
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
