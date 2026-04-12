"""Grafana plugin — visualization and dashboards."""

import json
import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
DASHBOARD_SCHEMA = {
    "type": "object",
    "properties": {"dashboard_json": {"type": "string"}},
    "required": ["dashboard_json"],
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


@register_plugin("grafana")
class GrafanaPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"grafana/grafana:{version}",
            "environment": {
                "GF_SECURITY_ADMIN_USER": credentials["user"],
                "GF_SECURITY_ADMIN_PASSWORD": credentials["password"],
                "GF_USERS_ALLOW_SIGN_UP": "false",
                # Enable anonymous access so the browser Quick Access link
                # opens straight into a working dashboard without a login
                # prompt. The anonymous viewer is given Admin role because
                # this is a disposable dev sandbox — not production.
                "GF_AUTH_ANONYMOUS_ENABLED": "true",
                "GF_AUTH_ANONYMOUS_ORG_ROLE": "Admin",
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/grafana", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:3000/api/health || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "GRAFANA_URL": f"http://{host}:3000",
            "GRAFANA_HOST": host,
            "GRAFANA_PORT": "3000",
            "GRAFANA_USER": credentials["user"],
            "GRAFANA_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        user = credentials["user"]
        password = credentials["password"]

        def _make_list_dashboards(cid, dr, u, p):
            async def handler(params: dict) -> str:
                cmd = f"curl -sf -u {u}:{p} 'http://localhost:3000/api/search?type=dash-db'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_create_dashboard(cid, dr, u, p):
            async def handler(params: dict) -> str:
                dashboard_json = _quote(params["dashboard_json"])
                cmd = f"curl -sf -u {u}:{p} -H 'Content-Type: application/json' -X POST 'http://localhost:3000/api/dashboards/db' -d '{dashboard_json}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("grafana_list_dashboards", "List dashboards", EMPTY_SCHEMA,
                      _make_list_dashboards(container_id, docker_runtime, user, password)),
            AgentTool("grafana_create_dashboard", "Create a dashboard", DASHBOARD_SCHEMA,
                      _make_create_dashboard(container_id, docker_runtime, user, password)),
        ]

    def generate_credentials(self, config):
        return {
            "user": "admin",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
