"""Plugin dependency auto-resolution — automatically install required dependencies."""

from __future__ import annotations

from typing import Any

import structlog

from pysandbox.plugin.registry import get_manifest, is_registered

logger = structlog.get_logger()


class DependencyResolver:
    """Resolves plugin dependencies and builds install order."""

    @staticmethod
    def resolve(
        requested_plugins: list[dict[str, Any]],
        installed_plugin_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve dependencies for a list of plugins.

        Returns the full list including auto-resolved dependencies,
        sorted in correct install order.
        """
        installed = installed_plugin_ids or set()
        requested_ids = {p["plugin_id"] for p in requested_plugins}
        all_plugins: dict[str, dict[str, Any]] = {}

        # Index requested plugins
        for p in requested_plugins:
            all_plugins[p["plugin_id"]] = p

        # Recursively resolve dependencies
        to_resolve = list(requested_ids)
        resolved_order: list[str] = []
        visited: set[str] = set()

        while to_resolve:
            pid = to_resolve.pop(0)
            if pid in visited:
                continue
            visited.add(pid)

            # Load manifest to find depends_on
            try:
                manifest = get_manifest(pid)
            except Exception:
                # If we can't load manifest, skip dependency resolution for this plugin
                if pid not in all_plugins:
                    all_plugins[pid] = {"plugin_id": pid, "name": pid, "expose": True}
                resolved_order.append(pid)
                continue

            deps = manifest.depends_on or []
            for dep in deps:
                if dep not in installed and dep not in visited:
                    to_resolve.insert(0, dep)  # Process deps first
                    if dep not in all_plugins:
                        # Auto-add dependency with defaults
                        all_plugins[dep] = {
                            "plugin_id": dep,
                            "name": dep,
                            "expose": True,
                            "auto_resolved": True,
                        }
                        logger.info("dependency_auto_resolved", plugin=pid, dependency=dep)

            if pid not in all_plugins:
                all_plugins[pid] = {"plugin_id": pid, "name": pid, "expose": True}
            resolved_order.append(pid)

        # Remove duplicates preserving order
        seen: set[str] = set()
        unique_order: list[str] = []
        for pid in resolved_order:
            if pid not in seen:
                seen.add(pid)
                unique_order.append(pid)

        # Build result with correct startup_order
        result = []
        for i, pid in enumerate(unique_order):
            if pid in installed:
                continue
            plugin_spec = dict(all_plugins[pid])
            # Set startup_order based on resolution order
            if "startup_order" not in plugin_spec:
                plugin_spec["startup_order"] = (i + 1) * 10
            result.append(plugin_spec)

        return result

    @staticmethod
    def get_dependency_tree(plugin_id: str) -> dict[str, Any]:
        """Get the full dependency tree for a plugin."""
        try:
            manifest = get_manifest(plugin_id)
        except Exception:
            return {"plugin_id": plugin_id, "dependencies": []}

        deps = []
        for dep_id in (manifest.depends_on or []):
            deps.append(DependencyResolver.get_dependency_tree(dep_id))

        return {
            "plugin_id": plugin_id,
            "display_name": manifest.display_name,
            "dependencies": deps,
        }
