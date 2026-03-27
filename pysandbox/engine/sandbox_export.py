"""Sandbox Export/Import — serialize sandbox config as portable YAML/JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class SandboxExporter:
    """Export and import sandbox configurations."""

    @staticmethod
    def export_config(sandbox: dict[str, Any], instances: list[dict[str, Any]]) -> dict[str, Any]:
        """Export sandbox configuration as a portable dict (can be serialized to YAML/JSON)."""
        plugins = []
        for inst in instances:
            plugins.append({
                "plugin_id": inst.get("plugin_id"),
                "name": inst.get("plugin_name"),
                "version": inst.get("version"),
                "config": inst.get("config", {}),
                "startup_order": inst.get("startup_order", 50),
                "expose": bool(inst.get("host_port") or inst.get("host_ports")),
            })

        # Sort by startup_order
        plugins.sort(key=lambda p: p.get("startup_order", 50))

        return {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sandbox": {
                "name": sandbox.get("name", "exported-sandbox"),
                "tags": sandbox.get("tags", {}),
                "total_cpu": sandbox.get("total_cpu"),
                "total_memory_gb": sandbox.get("total_memory_gb"),
                "total_disk_gb": sandbox.get("total_disk_gb"),
            },
            "plugins": plugins,
        }

    @staticmethod
    def import_config(config: dict[str, Any]) -> dict[str, Any]:
        """Parse an imported config into a sandbox creation request."""
        sb = config.get("sandbox", {})
        plugins = config.get("plugins", [])

        return {
            "name": sb.get("name", "imported-sandbox"),
            "tags": {**sb.get("tags", {}), "imported": "true"},
            "plugins": [
                {
                    "plugin_id": p["plugin_id"],
                    "name": p.get("name", p["plugin_id"]),
                    "version": p.get("version"),
                    "config": p.get("config", {}),
                    "expose": p.get("expose", True),
                    "startup_order": p.get("startup_order", 50),
                }
                for p in plugins
            ],
        }

    @staticmethod
    def validate_import(config: dict[str, Any]) -> list[str]:
        """Validate import config. Returns list of errors (empty = valid)."""
        errors = []
        if not isinstance(config, dict):
            return ["Config must be a dict"]
        if "plugins" not in config:
            errors.append("Missing 'plugins' key")
        if "sandbox" not in config:
            errors.append("Missing 'sandbox' key")

        for i, p in enumerate(config.get("plugins", [])):
            if not p.get("plugin_id"):
                errors.append(f"Plugin {i}: missing 'plugin_id'")
        return errors
