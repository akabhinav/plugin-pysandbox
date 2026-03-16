"""Jaeger plugin — distributed tracing."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
TRACE_SCHEMA = {
    "type": "object",
    "properties": {
        "service": {"type": "string"},
        "limit": {"type": "integer", "default": 20},
    },
    "required": ["service"],
}


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


@register_plugin("jaeger")
class JaegerPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"jaegertracing/all-in-one:{version}",
            "environment": {
                "COLLECTOR_OTLP_ENABLED": "true",
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "wget -qO- http://localhost:14269/ || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "JAEGER_URL": f"http://{host}:16686",
            "JAEGER_HOST": host,
            "JAEGER_QUERY_PORT": "16686",
            "JAEGER_COLLECTOR_PORT": "14268",
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{host}:4317",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = f"http://{plugin_name}.{dns_zone}:16686"
        return [
            AgentTool("jaeger_traces", "Search traces", TRACE_SCHEMA, _handler("jaeger_traces", url)),
            AgentTool("jaeger_services", "List traced services", EMPTY_SCHEMA, _handler("jaeger_services", url)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
