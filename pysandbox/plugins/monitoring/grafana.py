"""Grafana plugin — visualization and dashboards."""

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


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


@register_plugin("grafana")
class GrafanaPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"grafana/grafana:{version}",
            "environment": {
                "GF_SECURITY_ADMIN_USER": credentials["user"],
                "GF_SECURITY_ADMIN_PASSWORD": credentials["password"],
                "GF_USERS_ALLOW_SIGN_UP": "false",
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/grafana", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:3000/api/health || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = f"http://{plugin_name}.{dns_zone}:3000"
        return [
            AgentTool("grafana_list_dashboards", "List dashboards", EMPTY_SCHEMA, _handler("grafana_list_dashboards", url)),
            AgentTool("grafana_create_dashboard", "Create a dashboard", DASHBOARD_SCHEMA, _handler("grafana_create_dashboard", url)),
        ]

    def generate_credentials(self, config):
        return {
            "user": "admin",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
