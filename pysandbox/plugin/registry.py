"""Plugin registry — auto-discovers and registers all plugins via decorator."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Type

import yaml

from pysandbox.plugin.base import PluginDefinition
from pysandbox.plugin.exceptions import ManifestValidationError, PluginNotFoundError
from pysandbox.plugin.manifest import PluginManifest

import structlog

logger = structlog.get_logger()

# Global registry: plugin_id → class, plugin_id → manifest
_registry: dict[str, Type[PluginDefinition]] = {}
_manifests: dict[str, PluginManifest] = {}


def _find_manifest_path(plugin_id: str, manifest_path: str | None) -> Path:
    """Locate the YAML manifest for a plugin."""
    if manifest_path:
        return Path(manifest_path)

    # Search in plugin_manifests/{category}/{plugin_id}.yaml
    base = Path(__file__).parent.parent.parent / "plugin_manifests"
    for category_dir in base.iterdir():
        if not category_dir.is_dir():
            continue
        candidate = category_dir / f"{plugin_id}.yaml"
        if candidate.exists():
            return candidate

    raise ManifestValidationError(
        f"No manifest found for '{plugin_id}'. "
        f"Expected at plugin_manifests/{{category}}/{plugin_id}.yaml"
    )


def _load_manifest(plugin_id: str, manifest_path: str | None) -> PluginManifest:
    """Load and validate a plugin manifest from YAML."""
    path = _find_manifest_path(plugin_id, manifest_path)
    with open(path) as f:
        raw = yaml.safe_load(f)
    try:
        manifest = PluginManifest(**raw)
    except Exception as e:
        raise ManifestValidationError(f"Invalid manifest for '{plugin_id}': {e}") from e

    if manifest.id != plugin_id:
        raise ManifestValidationError(
            f"Manifest id '{manifest.id}' doesn't match plugin_id '{plugin_id}'"
        )
    return manifest


def register_plugin(plugin_id: str, manifest_path: str | None = None):
    """Decorator: @register_plugin("postgres") — loads YAML, validates, registers."""

    def decorator(cls: Type[PluginDefinition]) -> Type[PluginDefinition]:
        manifest = _load_manifest(plugin_id, manifest_path)
        cls.manifest = manifest
        _registry[plugin_id] = cls
        _manifests[plugin_id] = manifest
        logger.info("plugin_registered", plugin_id=plugin_id, display=manifest.display_name)
        return cls

    return decorator


def get_plugin(plugin_id: str) -> PluginDefinition:
    """Get a fresh instance of a registered plugin."""
    if plugin_id not in _registry:
        raise PluginNotFoundError(
            f"Plugin '{plugin_id}' not registered. Available: {list(_registry)}"
        )
    return _registry[plugin_id]()


def get_plugin_class(plugin_id: str) -> Type[PluginDefinition]:
    """Get the plugin class (not an instance)."""
    if plugin_id not in _registry:
        raise PluginNotFoundError(f"Plugin '{plugin_id}' not registered.")
    return _registry[plugin_id]


def get_manifest(plugin_id: str) -> PluginManifest:
    """Get the manifest for a registered plugin."""
    if plugin_id not in _manifests:
        raise PluginNotFoundError(f"Plugin '{plugin_id}' not registered.")
    return _manifests[plugin_id]


def list_plugins() -> list[PluginManifest]:
    """Return all registered plugin manifests."""
    return list(_manifests.values())


def list_plugin_ids() -> list[str]:
    """Return all registered plugin IDs."""
    return list(_registry.keys())


def is_registered(plugin_id: str) -> bool:
    return plugin_id in _registry


def clear_registry():
    """Clear all registrations — used in tests."""
    _registry.clear()
    _manifests.clear()
