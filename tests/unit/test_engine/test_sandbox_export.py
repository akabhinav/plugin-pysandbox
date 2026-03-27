"""Tests for Sandbox Export/Import feature."""

import pytest

from pysandbox.engine.sandbox_export import SandboxExporter


class TestSandboxExporter:
    def _sample_sandbox(self):
        return {
            "id": "sb-123",
            "name": "test-sandbox",
            "status": "running",
            "docker_network": "pysb-123",
            "dns_zone": "123.sandbox.local",
            "tags": {"env": "dev"},
            "total_cpu": 4.0,
            "total_memory_gb": 8.0,
            "total_disk_gb": 50.0,
        }

    def _sample_instances(self):
        return [
            {
                "plugin_id": "postgres",
                "plugin_name": "postgres",
                "version": "16",
                "config": {"max_connections": 100},
                "startup_order": 10,
                "host_port": 20001,
                "host_ports": {5432: 20001},
            },
            {
                "plugin_id": "redis",
                "plugin_name": "redis",
                "version": "7",
                "config": {},
                "startup_order": 20,
                "host_port": None,
                "host_ports": {},
            },
        ]

    def test_export_config(self):
        config = SandboxExporter.export_config(
            self._sample_sandbox(), self._sample_instances()
        )
        assert config["version"] == "1.0"
        assert config["exported_at"]
        assert config["sandbox"]["name"] == "test-sandbox"
        assert len(config["plugins"]) == 2
        assert config["plugins"][0]["plugin_id"] == "postgres"
        assert config["plugins"][0]["expose"] is True
        assert config["plugins"][1]["plugin_id"] == "redis"
        assert config["plugins"][1]["expose"] is False

    def test_export_sorted_by_startup_order(self):
        instances = self._sample_instances()
        instances[0]["startup_order"] = 20
        instances[1]["startup_order"] = 10
        config = SandboxExporter.export_config(self._sample_sandbox(), instances)
        assert config["plugins"][0]["plugin_id"] == "redis"
        assert config["plugins"][1]["plugin_id"] == "postgres"

    def test_import_config(self):
        export = SandboxExporter.export_config(
            self._sample_sandbox(), self._sample_instances()
        )
        result = SandboxExporter.import_config(export)
        assert result["name"] == "test-sandbox"
        assert "imported" in result["tags"]
        assert len(result["plugins"]) == 2

    def test_validate_import_valid(self):
        config = {
            "sandbox": {"name": "test"},
            "plugins": [{"plugin_id": "redis"}],
        }
        errors = SandboxExporter.validate_import(config)
        assert len(errors) == 0

    def test_validate_import_missing_plugins(self):
        config = {"sandbox": {"name": "test"}}
        errors = SandboxExporter.validate_import(config)
        assert any("plugins" in e for e in errors)

    def test_validate_import_missing_sandbox(self):
        config = {"plugins": [{"plugin_id": "redis"}]}
        errors = SandboxExporter.validate_import(config)
        assert any("sandbox" in e for e in errors)

    def test_validate_import_missing_plugin_id(self):
        config = {
            "sandbox": {"name": "test"},
            "plugins": [{"name": "redis"}],
        }
        errors = SandboxExporter.validate_import(config)
        assert any("plugin_id" in e for e in errors)

    def test_validate_import_not_dict(self):
        errors = SandboxExporter.validate_import("invalid")
        assert any("dict" in e for e in errors)

    def test_roundtrip(self):
        """Export then import should produce a valid creation request."""
        export = SandboxExporter.export_config(
            self._sample_sandbox(), self._sample_instances()
        )
        errors = SandboxExporter.validate_import(export)
        assert len(errors) == 0
        result = SandboxExporter.import_config(export)
        assert result["name"] == "test-sandbox"
        assert len(result["plugins"]) == 2
