"""Prometheus plugin — metrics collection and alerting."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginConnection, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "PromQL query"}},
    "required": ["query"],
}


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


@register_plugin("prometheus")
class PrometheusPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"prom/prometheus:{version}",
            "command": [
                "--config.file=/etc/prometheus/prometheus.yml",
                "--storage.tsdb.path=/prometheus",
                "--storage.tsdb.retention.time=7d",
                "--web.enable-lifecycle",
            ],
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/prometheus", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "wget -qO- http://localhost:9090/-/healthy || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "PROMETHEUS_URL": f"http://{host}:9090",
            "PROMETHEUS_HOST": host,
            "PROMETHEUS_PORT": "9090",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = f"http://{plugin_name}.{dns_zone}:9090"
        return [
            AgentTool("prometheus_query", "Run a PromQL instant query", QUERY_SCHEMA, _handler("prometheus_query", url)),
            AgentTool("prometheus_query_range", "Run a PromQL range query", QUERY_SCHEMA, _handler("prometheus_query_range", url)),
            AgentTool("prometheus_targets", "List scrape targets", EMPTY_SCHEMA, _handler("prometheus_targets", url)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []

    def on_plugin_event(self, event_type, plugin_id, connection):
        """Auto-add scrape targets when new plugins install."""
        # In a full implementation, this would update prometheus.yml
        pass
