"""PySandbox CLI — manage sandboxes from the command line."""

from __future__ import annotations

import json
from typing import Optional

import httpx
import typer

app = typer.Typer(name="pysandbox", help="Plugin-based enterprise sandbox runtime")

BASE_URL = "http://localhost:18080"


def _api(method: str, path: str, **kwargs) -> dict:
    """Make an API request and return JSON response."""
    url = f"{BASE_URL}{path}"
    resp = httpx.request(method, url, **kwargs)
    resp.raise_for_status()
    return resp.json()


@app.command()
def create(
    name: str = typer.Argument(..., help="Sandbox name"),
    plugin: list[str] = typer.Option([], "--plugin", "-p", help="Plugin specs: plugin_id:key=val,key=val"),
):
    """Create a new sandbox with optional plugins."""
    plugins = []
    for p in plugin:
        parts = p.split(":", 1)
        plugin_id = parts[0]
        config = {}
        if len(parts) > 1:
            for kv in parts[1].split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    config[k] = v
        plugins.append({"plugin_id": plugin_id, "name": plugin_id, "config": config})

    result = _api("POST", "/v1/sandboxes", json={"name": name, "plugins": plugins})
    sandbox = result["sandbox"]
    typer.echo(f"Sandbox '{name}' created: {sandbox['id']}")
    typer.echo(f"  Status: {sandbox['status']}")
    typer.echo(f"  Network: {sandbox.get('docker_network', 'N/A')}")
    typer.echo(f"  DNS Zone: {sandbox.get('dns_zone', 'N/A')}")


@app.command()
def status(name_or_id: str = typer.Argument(..., help="Sandbox name or ID")):
    """Show sandbox status."""
    sandboxes = _api("GET", "/v1/sandboxes")["sandboxes"]
    sandbox = _find_sandbox(sandboxes, name_or_id)
    if not sandbox:
        typer.echo(f"Sandbox '{name_or_id}' not found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Sandbox: {sandbox['name']} ({sandbox['id'][:8]})")
    typer.echo(f"  Status: {sandbox['status']}")
    typer.echo(f"  Network: {sandbox.get('docker_network', 'N/A')}")
    typer.echo(f"  DNS Zone: {sandbox.get('dns_zone', 'N/A')}")

    # List plugins
    result = _api("GET", f"/v1/sandboxes/{sandbox['id']}/plugins")
    for p in result.get("plugins", []):
        typer.echo(f"  Plugin: {p['plugin_name']} ({p['plugin_id']}) - {p['status']}")


@app.command()
def install(
    sandbox: str = typer.Argument(..., help="Sandbox name or ID"),
    plugin_id: str = typer.Argument(..., help="Plugin ID to install"),
    name: Optional[str] = typer.Option(None, help="Instance name"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Plugin version"),
):
    """Install a plugin into a sandbox."""
    sid = _resolve_sandbox_id(sandbox)
    body = {"plugin_id": plugin_id, "name": name or plugin_id, "version": version}
    result = _api("POST", f"/v1/sandboxes/{sid}/plugins", json=body)
    typer.echo(f"Installed {plugin_id} as '{result['plugin_name']}' at {result['dns_name']}")


@app.command()
def remove(
    sandbox: str = typer.Argument(..., help="Sandbox name or ID"),
    plugin_name: str = typer.Argument(..., help="Plugin instance name"),
):
    """Remove a plugin from a sandbox."""
    sid = _resolve_sandbox_id(sandbox)
    _api("DELETE", f"/v1/sandboxes/{sid}/plugins/{plugin_name}")
    typer.echo(f"Removed '{plugin_name}'")


@app.command(name="plugins")
def list_plugins(sandbox: str = typer.Argument(..., help="Sandbox name or ID")):
    """List installed plugins and their health."""
    sid = _resolve_sandbox_id(sandbox)
    result = _api("GET", f"/v1/sandboxes/{sid}/plugins")
    if not result.get("plugins"):
        typer.echo("No plugins installed")
        return
    for p in result["plugins"]:
        typer.echo(f"  {p['plugin_name']:20s} {p['plugin_id']:15s} {p['status']:10s} port:{p.get('host_port', 'N/A')}")


@app.command()
def catalog():
    """Browse available plugins."""
    result = _api("GET", "/v1/catalog")
    for p in result["plugins"]:
        typer.echo(f"  {p['id']:20s} {p['category']:12s} {p['display_name']}")
    typer.echo(f"\nTotal: {result['total']} plugins available")


@app.command()
def pause(sandbox: str = typer.Argument(..., help="Sandbox name or ID")):
    """Pause a sandbox."""
    sid = _resolve_sandbox_id(sandbox)
    _api("POST", f"/v1/sandboxes/{sid}/pause")
    typer.echo(f"Sandbox paused")


@app.command()
def resume(sandbox: str = typer.Argument(..., help="Sandbox name or ID")):
    """Resume a paused sandbox."""
    sid = _resolve_sandbox_id(sandbox)
    _api("POST", f"/v1/sandboxes/{sid}/resume")
    typer.echo(f"Sandbox resumed")


@app.command()
def destroy(sandbox: str = typer.Argument(..., help="Sandbox name or ID")):
    """Destroy a sandbox and all plugins."""
    sid = _resolve_sandbox_id(sandbox)
    _api("DELETE", f"/v1/sandboxes/{sid}")
    typer.echo(f"Sandbox destroyed")


@app.command()
def tools(sandbox: str = typer.Argument(..., help="Sandbox name or ID")):
    """List all agent tools for a sandbox."""
    sid = _resolve_sandbox_id(sandbox)
    result = _api("GET", f"/v1/sandboxes/{sid}/agent/tools")
    for t in result["tools"]:
        typer.echo(f"  {t['name']:30s} {t['description']}")
    typer.echo(f"\nTotal: {result['total']} tools")


def _resolve_sandbox_id(name_or_id: str) -> str:
    sandboxes = _api("GET", "/v1/sandboxes")["sandboxes"]
    sandbox = _find_sandbox(sandboxes, name_or_id)
    if not sandbox:
        typer.echo(f"Sandbox '{name_or_id}' not found", err=True)
        raise typer.Exit(1)
    return sandbox["id"]


def _find_sandbox(sandboxes: list[dict], name_or_id: str) -> dict | None:
    for s in sandboxes:
        if s["name"] == name_or_id or s["id"] == name_or_id or s["id"].startswith(name_or_id):
            return s
    return None


if __name__ == "__main__":
    app()
