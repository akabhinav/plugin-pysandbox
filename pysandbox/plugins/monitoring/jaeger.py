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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


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
                "start_period": 30_000_000_000,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):

        def _make_traces(cid, dr):
            async def handler(params: dict) -> str:
                service = _quote(params["service"])
                limit = params.get("limit", 20)
                cmd = f"wget -qO- 'http://localhost:16686/api/traces?service={service}&limit={limit}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_services(cid, dr):
            async def handler(params: dict) -> str:
                cmd = "wget -qO- 'http://localhost:16686/api/services'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("jaeger_traces", "Search traces", TRACE_SCHEMA,
                      _make_traces(container_id, docker_runtime)),
            AgentTool("jaeger_services", "List traced services", EMPTY_SCHEMA,
                      _make_services(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
