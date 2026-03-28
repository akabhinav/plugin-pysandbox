"""Tests for the Verify/Seed/Quickstart API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.verify import router, quickstart_router
    app = FastAPI()
    app.include_router(router)
    app.include_router(quickstart_router)

    engine = MagicMock()
    engine.get = AsyncMock(return_value={
        "id": "sb1", "name": "test", "status": "running",
        "tags": {"template": "microservices"},
    })
    app.state.sandbox_engine = engine

    verifier = MagicMock()
    verify_result = MagicMock()
    verify_result.to_dict.return_value = {
        "sandbox_id": "sb1",
        "success": True,
        "total": 5,
        "passed": 5,
        "failed": 0,
        "skipped": 0,
        "duration_ms": 150,
        "steps": [],
    }
    verifier.verify = AsyncMock(return_value=verify_result)
    app.state.sandbox_verifier = verifier

    seeder = MagicMock()
    seed_result = MagicMock()
    seed_result.to_dict.return_value = {
        "sandbox_id": "sb1",
        "success": True,
        "total_steps": 3,
        "succeeded": 3,
        "failed": 0,
        "duration_ms": 200,
        "steps": [],
    }
    seeder.seed = AsyncMock(return_value=seed_result)
    app.state.sandbox_seeder = seeder

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestVerifyAPI:
    def test_verify_sandbox(self, client):
        resp = client.post("/v1/sandboxes/sb1/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 5

    def test_verify_sandbox_not_found(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value=None)
        resp = client.post("/v1/sandboxes/sb999/verify")
        assert resp.status_code == 404

    def test_verify_sandbox_not_running(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value={
            "id": "sb1", "status": "paused", "tags": {},
        })
        resp = client.post("/v1/sandboxes/sb1/verify")
        assert resp.status_code == 409


class TestSeedAPI:
    def test_seed_sandbox(self, client):
        resp = client.post("/v1/sandboxes/sb1/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_steps"] == 3

    def test_seed_sandbox_not_found(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value=None)
        resp = client.post("/v1/sandboxes/sb999/seed")
        assert resp.status_code == 404

    def test_seed_sandbox_not_running(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value={
            "id": "sb1", "status": "destroyed", "tags": {},
        })
        resp = client.post("/v1/sandboxes/sb1/seed")
        assert resp.status_code == 409


class TestQuickstartAPI:
    def test_get_quickstart(self, client):
        resp = client.get("/v1/sandboxes/sb1/quickstart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["template_id"] == "microservices"
        assert data["total_steps"] > 0

    def test_get_quickstart_no_template(self, client, app):
        app.state.sandbox_engine.get = AsyncMock(return_value={
            "id": "sb1", "status": "running", "tags": {},
        })
        resp = client.get("/v1/sandboxes/sb1/quickstart")
        assert resp.status_code == 404

    def test_list_quickstarts(self, client):
        resp = client.get("/v1/quickstarts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 7
        assert len(data["quickstarts"]) >= 7
