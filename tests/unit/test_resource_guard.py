"""Tests for resource quota enforcement."""

import pytest

from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.plugin.exceptions import PluginError
from pysandbox.plugin.manifest import HealthCheckSpec, PluginManifest, ResourceRequirements


def _make_manifest(cpu="0.5", memory="512m", disk_gb=2.0) -> PluginManifest:
    return PluginManifest(
        id="test",
        version="1.0.0",
        display_name="Test",
        description="Test plugin",
        category="databases",
        docker_image="test:latest",
        health_check=HealthCheckSpec(type="tcp", port=5432),
        resources=ResourceRequirements(cpu=cpu, memory=memory, disk_gb=disk_gb),
    )


class TestResourceGuard:
    def test_reserve_within_limits(self, resource_guard):
        """Plugin installs within quota succeed."""
        resource_guard.init_sandbox("sb1", max_cpu=4.0, max_memory_gb=8.0, max_disk_gb=50.0, max_plugins=20)
        manifest = _make_manifest(cpu="1.0", memory="1g", disk_gb=5.0)
        resource_guard.check_and_reserve("sb1", manifest)  # Should not raise

    def test_cpu_exceeded(self, resource_guard):
        """Exceeding CPU limit raises PluginError."""
        resource_guard.init_sandbox("sb1", max_cpu=1.0, max_memory_gb=8.0, max_disk_gb=50.0, max_plugins=20)
        manifest = _make_manifest(cpu="2.0")
        with pytest.raises(PluginError, match="CPU"):
            resource_guard.check_and_reserve("sb1", manifest)

    def test_memory_exceeded(self, resource_guard):
        """Exceeding memory limit raises PluginError."""
        resource_guard.init_sandbox("sb1", max_cpu=4.0, max_memory_gb=1.0, max_disk_gb=50.0, max_plugins=20)
        manifest = _make_manifest(memory="2g")
        with pytest.raises(PluginError, match="Memory"):
            resource_guard.check_and_reserve("sb1", manifest)

    def test_plugin_count_exceeded(self, resource_guard):
        """Exceeding max plugins raises PluginError."""
        resource_guard.init_sandbox("sb1", max_cpu=100, max_memory_gb=100, max_disk_gb=100, max_plugins=1)
        manifest = _make_manifest()
        resource_guard.check_and_reserve("sb1", manifest)
        with pytest.raises(PluginError, match="Max plugins"):
            resource_guard.check_and_reserve("sb1", manifest)

    def test_release_frees_resources(self, resource_guard):
        """Released resources allow new installs."""
        resource_guard.init_sandbox("sb1", max_cpu=1.0, max_memory_gb=8.0, max_disk_gb=50.0, max_plugins=20)
        manifest = _make_manifest(cpu="0.8")
        resource_guard.check_and_reserve("sb1", manifest)
        resource_guard.release("sb1", manifest)
        resource_guard.check_and_reserve("sb1", manifest)  # Should succeed now

    def test_no_quota_tracking(self, resource_guard):
        """Uninitialized sandbox allows anything."""
        manifest = _make_manifest(cpu="100.0")
        resource_guard.check_and_reserve("unknown", manifest)  # Should not raise
