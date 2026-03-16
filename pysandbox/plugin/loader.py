"""Plugin auto-discovery — walks pysandbox/plugins/ and imports all modules.

The @register_plugin decorators fire on import, populating the registry.
No manual registration required — just drop a file in the right directory.
"""

from __future__ import annotations

import importlib
import pkgutil

import structlog

logger = structlog.get_logger()


def discover_and_load_all() -> int:
    """Import all modules under pysandbox.plugins. Returns count of modules loaded."""
    import pysandbox.plugins as pkg

    loaded = 0
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            importlib.import_module(modname)
            loaded += 1
        except Exception:
            logger.exception("plugin_load_failed", module=modname)
    logger.info("plugins_discovered", count=loaded)
    return loaded
