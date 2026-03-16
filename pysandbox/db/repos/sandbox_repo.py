"""Sandbox repository — in-memory implementation (swap for SQLAlchemy in prod)."""

from __future__ import annotations

from typing import Any


class SandboxRepo:
    """In-memory sandbox store. Replace with SQLAlchemy for persistence."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, dict[str, Any]] = {}

    async def create(self, sandbox: dict[str, Any]) -> None:
        self._sandboxes[sandbox["id"]] = sandbox

    async def get(self, sandbox_id: str) -> dict[str, Any] | None:
        return self._sandboxes.get(sandbox_id)

    async def update(self, sandbox: dict[str, Any]) -> None:
        self._sandboxes[sandbox["id"]] = sandbox

    async def update_status(self, sandbox_id: str, status: str) -> None:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox:
            sandbox["status"] = status

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._sandboxes.values())

    async def mark_destroyed(self, sandbox_id: str) -> None:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox:
            sandbox["status"] = "destroyed"

    async def delete(self, sandbox_id: str) -> None:
        self._sandboxes.pop(sandbox_id, None)
