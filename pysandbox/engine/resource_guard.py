"""Resource quota enforcement per sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field

from pysandbox.plugin.exceptions import PluginError
from pysandbox.plugin.manifest import PluginManifest


def _parse_memory_mb(mem_str: str) -> float:
    """Convert Docker memory string (e.g. '512m', '2g') to MB."""
    mem_str = mem_str.strip().lower()
    if mem_str.endswith("g"):
        return float(mem_str[:-1]) * 1024
    if mem_str.endswith("m"):
        return float(mem_str[:-1])
    return float(mem_str)


@dataclass
class SandboxQuota:
    """Tracks resource usage for a single sandbox."""

    max_cpu: float
    max_memory_gb: float
    max_disk_gb: float
    max_plugins: int

    used_cpu: float = 0.0
    used_memory_mb: float = 0.0
    used_disk_gb: float = 0.0
    plugin_count: int = 0


class ResourceGuard:
    """Validates resource availability before plugin installs."""

    def __init__(self) -> None:
        self._quotas: dict[str, SandboxQuota] = {}

    def init_sandbox(
        self,
        sandbox_id: str,
        max_cpu: float,
        max_memory_gb: float,
        max_disk_gb: float,
        max_plugins: int,
    ) -> None:
        self._quotas[sandbox_id] = SandboxQuota(
            max_cpu=max_cpu,
            max_memory_gb=max_memory_gb,
            max_disk_gb=max_disk_gb,
            max_plugins=max_plugins,
        )

    def check_and_reserve(self, sandbox_id: str, manifest: PluginManifest) -> None:
        """Check if the sandbox has enough resources; reserve if yes."""
        quota = self._quotas.get(sandbox_id)
        if not quota:
            return  # No quota tracking for this sandbox

        req = manifest.resources
        cpu = float(req.cpu)
        mem = _parse_memory_mb(req.memory)
        disk = req.disk_gb

        if quota.plugin_count >= quota.max_plugins:
            raise PluginError(f"Max plugins ({quota.max_plugins}) reached")
        if quota.used_cpu + cpu > quota.max_cpu:
            raise PluginError(f"CPU limit exceeded: need {cpu}, available {quota.max_cpu - quota.used_cpu}")
        if quota.used_memory_mb + mem > quota.max_memory_gb * 1024:
            raise PluginError("Memory limit exceeded")
        if quota.used_disk_gb + disk > quota.max_disk_gb:
            raise PluginError("Disk limit exceeded")

        # Reserve
        quota.used_cpu += cpu
        quota.used_memory_mb += mem
        quota.used_disk_gb += disk
        quota.plugin_count += 1

    def release(self, sandbox_id: str, manifest: PluginManifest) -> None:
        """Release resources when a plugin is removed."""
        quota = self._quotas.get(sandbox_id)
        if not quota:
            return
        req = manifest.resources
        quota.used_cpu = max(0, quota.used_cpu - float(req.cpu))
        quota.used_memory_mb = max(0, quota.used_memory_mb - _parse_memory_mb(req.memory))
        quota.used_disk_gb = max(0, quota.used_disk_gb - req.disk_gb)
        quota.plugin_count = max(0, quota.plugin_count - 1)

    def remove_sandbox(self, sandbox_id: str) -> None:
        self._quotas.pop(sandbox_id, None)
