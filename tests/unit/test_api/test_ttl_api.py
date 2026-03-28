"""Tests for the TTL API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from pysandbox.engine.sandbox_ttl import SandboxTTLManager


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.ttl import router
    app = FastAPI()
    app.include_router(router)
    app.state.ttl_manager = SandboxTTLManager()

    engine = MagicMock()
    engine.get = AsyncMock(return_value={
        "id": "sb1", "name": "test", "status": "running",
    })
    app.state.sandbox_engine = engine
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTTLAPI:
    def test_set_ttl(self, client):
        resp = client.post("/v1/ttl/sb1", json={"ttl_seconds": 3600})
        assert resp.status_code == 200
        assert resp.json()["ttl_seconds"] == 3600

    def test_get_ttl(self, client):
        client.post("/v1/ttl/sb1", json={"ttl_seconds": 3600})
        resp = client.get("/v1/ttl/sb1")
        assert resp.status_code == 200
        assert resp.json()["remaining_seconds"] > 0

    def test_get_ttl_not_found(self, client):
        resp = client.get("/v1/ttl/sb999")
        assert resp.status_code == 404

    def test_set_ttl_too_short(self, client):
        resp = client.post("/v1/ttl/sb1", json={"ttl_seconds": 30})
        assert resp.status_code == 400

    def test_remove_ttl(self, client):
        client.post("/v1/ttl/sb1", json={"ttl_seconds": 3600})
        resp = client.delete("/v1/ttl/sb1")
        assert resp.status_code == 200

    def test_remove_ttl_not_found(self, client):
        resp = client.delete("/v1/ttl/sb999")
        assert resp.status_code == 404

    def test_list_ttls(self, client):
        client.post("/v1/ttl/sb1", json={"ttl_seconds": 3600})
        client.post("/v1/ttl/sb2", json={"ttl_seconds": 7200})
        resp = client.get("/v1/ttl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
