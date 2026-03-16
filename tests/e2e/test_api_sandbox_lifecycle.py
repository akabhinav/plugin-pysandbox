"""End-to-end API tests using TestClient."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked Docker runtime."""
    import os
    os.environ.setdefault("PYSANDBOX_MASTER_KEY", "test-key")
    os.environ.setdefault("SECRET_ENCRYPTION_KEY", "")

    from pysandbox.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestCatalogEndpoints:
    def test_list_catalog(self, client):
        """Catalog lists all registered plugins."""
        resp = client.get("/v1/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 10
        ids = {p["id"] for p in data["plugins"]}
        assert "postgres" in ids
        assert "redis" in ids
        assert "kafka" in ids

    def test_get_plugin_details(self, client):
        """Individual plugin details are accessible."""
        resp = client.get("/v1/catalog/postgres")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "postgres"
        assert data["category"] == "databases"

    def test_get_unknown_plugin(self, client):
        resp = client.get("/v1/catalog/nonexistent")
        assert resp.status_code == 404

    def test_get_plugin_schema(self, client):
        resp = client.get("/v1/catalog/postgres/schema")
        assert resp.status_code == 200
        assert resp.json()["plugin_id"] == "postgres"


class TestSandboxEndpoints:
    def test_list_sandboxes_empty(self, client):
        resp = client.get("/v1/sandboxes")
        assert resp.status_code == 200
        assert resp.json()["sandboxes"] == []

    def test_get_nonexistent_sandbox(self, client):
        resp = client.get("/v1/sandboxes/nonexistent-id")
        assert resp.status_code == 404
