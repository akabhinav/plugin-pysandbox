"""Per-sandbox environment variable management."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class EnvInjector:
    """Tracks env vars per sandbox. Plugins inject, agent and other plugins read."""

    def __init__(self) -> None:
        # sandbox_id → {key → value}
        self._env: dict[str, dict[str, str]] = {}

    async def inject(self, sandbox_id: str, env_vars: dict[str, str]) -> None:
        """Add env vars to a sandbox's environment."""
        self._env.setdefault(sandbox_id, {}).update(env_vars)
        logger.debug("env_injected", sandbox_id=sandbox_id, keys=list(env_vars))

    async def remove(self, sandbox_id: str, keys: list[str]) -> None:
        """Remove specific env vars from a sandbox."""
        sandbox_env = self._env.get(sandbox_id, {})
        for key in keys:
            sandbox_env.pop(key, None)

    def get_all(self, sandbox_id: str) -> dict[str, str]:
        """Get all env vars for a sandbox."""
        return dict(self._env.get(sandbox_id, {}))

    def get_redacted(self, sandbox_id: str) -> dict[str, str]:
        """Get env vars with secret values redacted."""
        env = self._env.get(sandbox_id, {})
        secret_keywords = {"PASSWORD", "SECRET", "TOKEN", "KEY"}
        return {
            k: ("***" if any(s in k.upper() for s in secret_keywords) else v)
            for k, v in env.items()
        }

    def clear_sandbox(self, sandbox_id: str) -> None:
        self._env.pop(sandbox_id, None)
