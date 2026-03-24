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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):

        def _make_query(cid, dr):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"wget -qO- 'http://localhost:9090/api/v1/query?query={query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_query_range(cid, dr):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"wget -qO- 'http://localhost:9090/api/v1/query_range?query={query}&start=now-1h&end=now&step=15s'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_targets(cid, dr):
            async def handler(params: dict) -> str:
                cmd = "wget -qO- 'http://localhost:9090/api/v1/targets'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("prometheus_query", "Run a PromQL instant query", QUERY_SCHEMA,
                      _make_query(container_id, docker_runtime)),
            AgentTool("prometheus_query_range", "Run a PromQL range query", QUERY_SCHEMA,
                      _make_query_range(container_id, docker_runtime)),
            AgentTool("prometheus_targets", "List scrape targets", EMPTY_SCHEMA,
                      _make_targets(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []

    def on_plugin_event(self, event_type, plugin_id, connection):
        pass
