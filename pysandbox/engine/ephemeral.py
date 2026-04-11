"""Ephemeral sandboxes — zero-config short-URL launcher with auto-destruct.

The classic `POST /v1/sandboxes` endpoint takes a structured body; this
feature is aimed at the "one-liner in a Slack message" use case. You
give it a list of plugin IDs and maybe a template, and it:

1. resolves the stack to a full plugin spec
2. creates the sandbox with a short human-friendly ID
3. sets a default TTL (30 minutes) so abandoned sandboxes clean up
4. returns a URL-safe handle + all the auto-generated credentials

The URL-safe "short ID" is a 6-character base32 encoding of random bytes.
We check it against the active sandbox registry on creation to avoid
collisions — the birthday bound at 6 chars is ~33k sandboxes, which is
fine for this intended use case (ephemeral dev links, not permanent).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any


# Curated preset stacks so users can type `?stack=microservices` instead
# of listing every plugin. These are deliberately smaller than the full
# template registry — the goal is a fast, one-off sandbox.
PRESET_STACKS: dict[str, list[str]] = {
    "web": ["postgres", "redis"],
    "web-messaging": ["postgres", "redis", "rabbitmq"],
    "microservices": ["postgres", "redis", "kafka"],
    "data": ["postgres", "minio"],
    "lakehouse": ["minio", "spark"],
    "observability": ["prometheus", "grafana", "jaeger"],
    "graph": ["neo4j"],
    "search": ["elasticsearch"],
    "ml": ["postgres", "minio"],
}


# Character alphabet for short IDs. Base32 minus the ambiguous 0/O/1/I/L
# so short codes are safe to read over a phone or paste from a screenshot.
_SHORT_ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _gen_short_id(length: int = 6) -> str:
    """Return a random short ID like `x7k9m2` suitable for URLs."""
    return "".join(secrets.choice(_SHORT_ID_ALPHABET) for _ in range(length))


@dataclass
class EphemeralSpec:
    """Normalized ephemeral sandbox request."""

    plugins: list[str]
    ttl_seconds: int
    name: str | None = None
    owner_id: str = "ephemeral"
    short_id: str | None = None


def resolve_stack(stack: str | None, plugin_list: list[str] | None) -> list[str]:
    """Turn the user-facing `stack=` argument into an actual plugin list.

    If `stack` is a known preset name, use it. Otherwise treat it as a
    comma or plus delimited list: `postgres+redis` or `postgres,redis`.
    Explicit `plugin_list` wins if provided.
    """
    if plugin_list:
        return [p.strip() for p in plugin_list if p and p.strip()]
    if not stack:
        return []
    if stack in PRESET_STACKS:
        return list(PRESET_STACKS[stack])
    # Fallback: split on + or , or whitespace.
    parts: list[str] = []
    for chunk in stack.replace(",", "+").split("+"):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def parse_ephemeral_request(
    *,
    stack: str | None = None,
    plugins: list[str] | None = None,
    ttl_seconds: int | None = None,
    name: str | None = None,
    max_ttl_seconds: int = 3600,
    default_ttl_seconds: int = 1800,
) -> EphemeralSpec:
    """Build an EphemeralSpec from user input, applying sane defaults.

    TTL is clamped to [60, max_ttl_seconds] so the endpoint can't be
    used to create effectively permanent sandboxes.
    """
    plugin_list = resolve_stack(stack, plugins)
    if not plugin_list:
        raise ValueError(
            "No plugins resolved — specify `stack=` (preset or plugin list) "
            "or `plugins=[...]`.",
        )
    ttl = ttl_seconds if ttl_seconds is not None else default_ttl_seconds
    ttl = max(60, min(int(ttl), max_ttl_seconds))
    return EphemeralSpec(
        plugins=plugin_list,
        ttl_seconds=ttl,
        name=name,
    )


class EphemeralSandboxLauncher:
    """High-level facade: create a sandbox + set TTL in one call.

    The launcher doesn't touch Docker directly — it composes the existing
    SandboxEngine and SandboxTTLManager. Keeping it thin means bug fixes
    in either of those modules flow through automatically.
    """

    def __init__(
        self,
        sandbox_engine,
        ttl_manager,
        *,
        short_id_registry: set[str] | None = None,
        max_ttl_seconds: int = 3600,
        default_ttl_seconds: int = 1800,
    ) -> None:
        self._engine = sandbox_engine
        self._ttl = ttl_manager
        self._short_ids = short_id_registry if short_id_registry is not None else set()
        self._max_ttl = max_ttl_seconds
        self._default_ttl = default_ttl_seconds

    async def launch(self, spec: EphemeralSpec) -> dict[str, Any]:
        """Create the sandbox, set TTL, and return a URL-safe record."""
        short_id = self._allocate_short_id()
        name = spec.name or f"eph-{short_id}"

        plugin_specs = [
            {
                "plugin_id": p,
                "name": p,
                "version": self._best_version_for(p),
                "expose": True,
                "config": {},
            }
            for p in spec.plugins
        ]
        sandbox = await self._engine.create(
            name=name,
            owner_id=spec.owner_id,
            plugins=plugin_specs,
            tags={"ephemeral": "true", "short_id": short_id},
        )
        ttl_info = self._ttl.set_ttl(sandbox["id"], spec.ttl_seconds)

        return {
            "short_id": short_id,
            "sandbox_id": sandbox["id"],
            "name": sandbox["name"],
            "status": sandbox["status"],
            "plugins": spec.plugins,
            "expires_in_seconds": spec.ttl_seconds,
            "expires_at": ttl_info["expires_at"],
            "dns_zone": sandbox.get("dns_zone"),
        }

    async def launch_from_request(
        self,
        *,
        stack: str | None = None,
        plugins: list[str] | None = None,
        ttl_seconds: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Parse + launch in one call — what the `/spin` endpoint uses."""
        spec = parse_ephemeral_request(
            stack=stack,
            plugins=plugins,
            ttl_seconds=ttl_seconds,
            name=name,
            max_ttl_seconds=self._max_ttl,
            default_ttl_seconds=self._default_ttl,
        )
        return await self.launch(spec)

    def _allocate_short_id(self, max_attempts: int = 16) -> str:
        """Draw a unique short ID, retrying on collision."""
        for _ in range(max_attempts):
            candidate = _gen_short_id()
            if candidate not in self._short_ids:
                self._short_ids.add(candidate)
                return candidate
        # With 33k-candidate space and our attempt budget, collisions are
        # effectively impossible, but raise cleanly just in case.
        raise RuntimeError("Failed to allocate unique short ID after retries")

    def release_short_id(self, short_id: str) -> None:
        """Let the short ID be reused once the sandbox is destroyed."""
        self._short_ids.discard(short_id)

    def _best_version_for(self, plugin_id: str) -> str | None:
        """Pick the best version tag for an ephemeral sandbox.

        Some plugins (notably redis, nats) use a `{version}-alpine`
        image template where `{version}=latest` expands to an invalid
        tag like `redis:latest-alpine`. To make "one-click spin" always
        work, we prefer the first concrete version in `supported_versions`
        that isn't literally "latest". If the manifest only lists
        "latest", we fall through and let the plugin engine handle it.
        """
        try:
            # Local import: manifests are registered lazily, so importing
            # at module load time would create a chicken-and-egg with
            # plugin discovery.
            from pysandbox.plugin.registry import get_manifest
            manifest = get_manifest(plugin_id)
        except Exception:
            return None
        versions = list(manifest.supported_versions or [])
        for v in versions:
            if v and v.lower() != "latest":
                return v
        return manifest.default_version or None
