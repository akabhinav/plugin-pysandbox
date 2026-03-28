"""Tests for the Interactive Web Terminal API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.terminal import router
    app = FastAPI()
    app.include_router(router)

    docker = MagicMock()
    docker.exec_in_container = AsyncMock(return_value="hello world\n")
    app.state.docker_runtime = docker

    repo = MagicMock()
    repo.get_instance = AsyncMock(return_value={
        "plugin_name": "postgres",
        "plugin_id": "postgres",
        "container_id": "abc123",
        "status": "healthy",
    })
    repo.list_instances = AsyncMock(return_value=[
        {
            "plugin_name": "postgres",
            "plugin_id": "postgres",
            "container_id": "abc123",
            "status": "healthy",
        },
        {
            "plugin_name": "redis",
            "plugin_id": "redis",
            "container_id": "def456",
            "status": "healthy",
        },
    ])
    app.state.plugin_instance_repo = repo

    engine = MagicMock()
    engine.get = AsyncMock(return_value={
        "id": "sb1", "name": "test", "status": "running",
    })
    app.state.sandbox_engine = engine
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTerminalAPI:
    def test_exec_command(self, client):
        resp = client.post("/v1/terminal/sb1/postgres", json={"command": "echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "hello" in data["output"]

    def test_exec_command_plugin_not_found(self, client, app):
        app.state.plugin_instance_repo.get_instance = AsyncMock(return_value=None)
        resp = client.post("/v1/terminal/sb1/missing", json={"command": "echo hello"})
        assert resp.status_code == 404

    def test_list_terminals(self, client):
        resp = client.get("/v1/terminal/sb1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["terminals"]) == 2
        names = {t["plugin_name"] for t in data["terminals"]}
        assert "postgres" in names
        assert "redis" in names

    def test_exec_error(self, client, app):
        app.state.docker_runtime.exec_in_container = AsyncMock(side_effect=Exception("container died"))
        resp = client.post("/v1/terminal/sb1/postgres", json={"command": "bad"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
