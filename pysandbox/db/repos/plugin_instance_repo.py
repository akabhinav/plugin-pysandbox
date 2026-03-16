"""Plugin instance repository — in-memory implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class PluginInstanceRepo:
    """In-memory plugin instance store. Replace with SQLAlchemy for persistence."""

    def __init__(self) -> None:
        # sandbox_id → [instance_dicts]
        self._instances: dict[str, list[dict[str, Any]]] = {}

    async def create_instance(
        self,
        sandbox_id: str,
        plugin_id: str,
        plugin_name: str,
        version: str,
        config: dict,
        credentials_encrypted: str,
        container_id: str,
        container_ip: str,
        internal_port: int,
        host_port: int | None,
        env_var_keys: list[str],
        agent_tool_names: list[str],
        startup_order: int = 50,
    ) -> dict[str, Any]:
        instance = {
            "id": str(uuid4()),
            "sandbox_id": sandbox_id,
            "plugin_id": plugin_id,
            "plugin_name": plugin_name,
            "version": version,
            "status": "healthy",
            "container_id": container_id,
            "container_ip": container_ip,
            "internal_port": internal_port,
            "host_port": host_port,
            "config": config,
            "credentials_encrypted": credentials_encrypted,
            "env_var_keys": env_var_keys,
            "agent_tool_names": agent_tool_names,
            "startup_order": startup_order,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "removed_at": None,
        }
        self._instances.setdefault(sandbox_id, []).append(instance)
        return instance

    async def get_instance(self, sandbox_id: str, plugin_name: str) -> dict[str, Any] | None:
        for inst in self._instances.get(sandbox_id, []):
            if inst["plugin_name"] == plugin_name and inst["status"] != "removed":
                return inst
        return None

    async def list_instances(self, sandbox_id: str) -> list[dict[str, Any]]:
        return [i for i in self._instances.get(sandbox_id, []) if i["status"] != "removed"]

    async def mark_removed(self, sandbox_id: str, plugin_name: str) -> None:
        for inst in self._instances.get(sandbox_id, []):
            if inst["plugin_name"] == plugin_name:
                inst["status"] = "removed"
                inst["removed_at"] = datetime.now(timezone.utc).isoformat()

    async def update_status(self, sandbox_id: str, plugin_name: str, status: str) -> None:
        for inst in self._instances.get(sandbox_id, []):
            if inst["plugin_name"] == plugin_name:
                inst["status"] = status
