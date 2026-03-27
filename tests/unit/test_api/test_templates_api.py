"""Tests for the Templates API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from pysandbox.engine.templates import TemplateRegistry


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.templates import router
    app = FastAPI()
    app.include_router(router)
    app.state.template_registry = TemplateRegistry()
    app.state.sandbox_engine = MagicMock()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTemplatesAPI:
    def test_list_templates(self, client):
        resp = client.get("/v1/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert data["total"] >= 5

    def test_get_template(self, client):
        resp = client.get("/v1/templates/data-lakehouse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "data-lakehouse"
        assert "plugins" in data

    def test_get_template_not_found(self, client):
        resp = client.get("/v1/templates/nonexistent")
        assert resp.status_code == 404

    def test_register_custom_template(self, client):
        resp = client.post("/v1/templates", json={
            "id": "test-custom",
            "name": "Test Custom",
            "description": "A test template",
            "plugins": [
                {"plugin_id": "redis", "name": "redis", "expose": True},
                {"plugin_id": "postgres", "name": "postgres", "expose": True},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["template_id"] == "test-custom"

        # Should appear in list
        resp2 = client.get("/v1/templates")
        ids = [t["id"] for t in resp2.json()["templates"]]
        assert "test-custom" in ids

    def test_delete_custom_template(self, client):
        client.post("/v1/templates", json={
            "id": "to-delete",
            "name": "Delete Me",
            "description": "Will be deleted",
            "plugins": [{"plugin_id": "redis", "name": "redis", "expose": True},
                        {"plugin_id": "postgres", "name": "pg", "expose": True}],
        })
        resp = client.delete("/v1/templates/to-delete")
        assert resp.status_code == 200

    def test_delete_nonexistent_template(self, client):
        resp = client.delete("/v1/templates/nonexistent")
        assert resp.status_code == 404

    def test_launch_from_template(self, client, app):
        app.state.sandbox_engine.create = AsyncMock(return_value={"id": "sb1", "name": "test"})
        resp = client.post("/v1/templates/launch", json={
            "name": "my-lakehouse",
            "template_id": "data-lakehouse",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["template_id"] == "data-lakehouse"

    def test_launch_nonexistent_template(self, client):
        resp = client.post("/v1/templates/launch", json={
            "name": "test",
            "template_id": "nonexistent",
        })
        assert resp.status_code == 404
