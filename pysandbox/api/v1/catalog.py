"""Plugin catalog endpoints — browse available plugins."""

from fastapi import APIRouter, HTTPException

from pysandbox.plugin.registry import get_manifest, is_registered, list_plugins

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("")
async def list_catalog():
    """List all available plugins."""
    manifests = list_plugins()
    return {
        "plugins": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "description": m.description,
                "category": m.category,
                "tags": m.tags,
                "default_version": m.default_version,
                "supported_versions": m.supported_versions,
            }
            for m in manifests
        ],
        "total": len(manifests),
    }


@router.get("/{plugin_id}")
async def get_plugin_details(plugin_id: str):
    """Get full details of a specific plugin."""
    if not is_registered(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    manifest = get_manifest(plugin_id)
    return manifest.model_dump()


@router.get("/{plugin_id}/schema")
async def get_plugin_config_schema(plugin_id: str):
    """Get JSON Schema for plugin configuration."""
    if not is_registered(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    manifest = get_manifest(plugin_id)
    return {
        "plugin_id": plugin_id,
        "config_params": [p.model_dump() for p in manifest.config_params],
    }
