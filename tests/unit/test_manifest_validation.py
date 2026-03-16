"""Tests for plugin manifest validation."""

import pytest
from pydantic import ValidationError

from pysandbox.plugin.manifest import (
    ConfigParam,
    HealthCheckSpec,
    PluginManifest,
    PortSpec,
    ResourceRequirements,
)


class TestPluginManifest:
    def test_valid_minimal_manifest(self):
        """Minimal valid manifest passes validation."""
        m = PluginManifest(
            id="test",
            version="1.0.0",
            display_name="Test Plugin",
            description="A test plugin",
            category="databases",
            docker_image="test:latest",
            health_check=HealthCheckSpec(type="tcp", port=5432),
        )
        assert m.id == "test"
        assert m.default_version == "latest"

    def test_full_manifest(self):
        """Full manifest with all fields passes."""
        m = PluginManifest(
            id="postgres",
            version="1.0.0",
            display_name="PostgreSQL 16",
            description="PostgreSQL relational database",
            category="databases",
            tags=["relational", "sql", "acid"],
            docker_image="postgres:{version}",
            supported_versions=["16", "15", "14"],
            default_version="16",
            ports=[PortSpec(port=5432, protocol="tcp", name="postgres")],
            resources=ResourceRequirements(cpu="1.0", memory="1g", disk_gb=10.0),
            health_check=HealthCheckSpec(type="tcp", port=5432, retries=10),
            config_params=[
                ConfigParam(key="shared_buffers", type="string", default="128MB"),
            ],
            depends_on=[],
            startup_order=10,
            generates_credentials=True,
            persistent_data=True,
        )
        assert m.category == "databases"
        assert len(m.ports) == 1
        assert m.ports[0].port == 5432

    def test_invalid_category(self):
        """Invalid category is rejected."""
        with pytest.raises(ValidationError):
            PluginManifest(
                id="test",
                version="1.0.0",
                display_name="Test",
                description="Test",
                category="invalid_category",
                docker_image="test:latest",
                health_check=HealthCheckSpec(type="tcp", port=5432),
            )

    def test_missing_required_fields(self):
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            PluginManifest(id="test")  # Missing most required fields

    def test_health_check_types(self):
        """All health check types are accepted."""
        for hc_type in ["tcp", "http", "exec"]:
            hc = HealthCheckSpec(type=hc_type, port=8080)
            assert hc.type == hc_type

    def test_resource_defaults(self):
        """Resource requirements have sensible defaults."""
        r = ResourceRequirements()
        assert r.cpu == "0.5"
        assert r.memory == "512m"
        assert r.disk_gb == 2.0

    def test_port_spec(self):
        """Port spec validates correctly."""
        p = PortSpec(port=5432, protocol="tcp", name="postgres")
        assert p.port == 5432
        assert p.protocol == "tcp"

    def test_config_param(self):
        """Config params validate correctly."""
        p = ConfigParam(
            key="max_connections",
            type="int",
            required=False,
            default=200,
            description="Max DB connections",
            secret=False,
        )
        assert p.key == "max_connections"
        assert p.type == "int"

    def test_config_param_secret(self):
        """Secret config params are flagged."""
        p = ConfigParam(key="api_key", type="string", secret=True)
        assert p.secret is True
