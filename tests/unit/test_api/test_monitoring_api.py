"""Tests for the Monitoring API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from pysandbox.api.v1.monitoring import router
    app = FastAPI()
    app.include_router(router)

    docker = MagicMock()
    docker.get_container_stats = AsyncMock(return_value={
        "container_id": "abc123",
        "cpu_percent": 25.5,
        "memory_usage_mb": 256.0,
        "memory_limit_mb": 512.0,
        "memory_percent": 50.0,
        "network_rx_mb": 1.5,
        "network_tx_mb": 0.8,
    })
    docker.get_container_status = AsyncMock(return_value="healthy")
    docker.get_logs = AsyncMock(return_value="log line 1\nlog line 2\n")
    app.state.docker_runtime = docker

    repo = MagicMock()
    repo.list_instances = AsyncMock(return_value=[
        {
            "plugin_name": "postgres",
            "plugin_id": "postgres",
            "container_id": "abc123",
            "status": "healthy",
            "version": "16",
            "installed_at": "2024-01-01T00:00:00Z",
        },
    ])
    repo.get_instance = AsyncMock(return_value={
        "plugin_name": "postgres",
        "container_id": "abc123",
    })
    app.state.plugin_instance_repo = repo
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestMonitoringAPI:
    def test_get_resource_usage(self, client):
        resp = client.get("/v1/monitoring/resources/sb1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["container_count"] == 1
        stats = data["stats"][0]
        assert stats["cpu_percent"] == 25.5
        assert stats["memory_usage_mb"] == 256.0
        assert stats["plugin_name"] == "postgres"

    def test_get_resource_usage_not_found(self, client, app):
        app.state.plugin_instance_repo.list_instances = AsyncMock(return_value=[])
        resp = client.get("/v1/monitoring/resources/sb999")
        assert resp.status_code == 404

    def test_get_health_dashboard(self, client):
        resp = client.get("/v1/monitoring/health/sb1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["healthy"] == 1
        assert data["unhealthy"] == 0

    def test_get_plugin_logs(self, client):
        resp = client.get("/v1/monitoring/logs/sb1/postgres")
        assert resp.status_code == 200
        data = resp.json()
        assert "log line" in data["logs"]

    def test_get_plugin_logs_not_found(self, client, app):
        app.state.plugin_instance_repo.get_instance = AsyncMock(return_value=None)
        resp = client.get("/v1/monitoring/logs/sb1/missing")
        assert resp.status_code == 404
