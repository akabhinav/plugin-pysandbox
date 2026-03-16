"""Elasticsearch plugin — search and analytics engine."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "index": {"type": "string"},
        "query": {"type": "object"},
    },
    "required": ["index", "query"],
}
INDEX_DOC_SCHEMA = {
    "type": "object",
    "properties": {
        "index": {"type": "string"},
        "document": {"type": "object"},
    },
    "required": ["index", "document"],
}
INDEX_NAME_SCHEMA = {
    "type": "object",
    "properties": {"index": {"type": "string"}},
    "required": ["index"],
}


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


@register_plugin("elasticsearch")
class ElasticsearchPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"docker.elastic.co/elasticsearch/elasticsearch:{version}",
            "environment": {
                "discovery.type": "single-node",
                "ELASTIC_PASSWORD": credentials["password"],
                "xpack.security.enabled": "true",
                "ES_JAVA_OPTS": config.get("java_opts", "-Xms512m -Xmx512m"),
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/usr/share/elasticsearch/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", f"curl -sf -u elastic:{credentials['password']} http://localhost:9200/_cluster/health"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 12,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        url = f"http://elastic:{credentials['password']}@{host}:9200"
        return {
            "ELASTICSEARCH_URL": url,
            "ELASTICSEARCH_HOST": host,
            "ELASTICSEARCH_PORT": "9200",
            "ELASTICSEARCH_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = self.get_env_vars(plugin_name, dns_zone, credentials, config)["ELASTICSEARCH_URL"]
        return [
            AgentTool("es_search", "Search documents", SEARCH_SCHEMA, _handler("es_search", url)),
            AgentTool("es_index", "Index a document", INDEX_DOC_SCHEMA, _handler("es_index", url)),
            AgentTool("es_delete_index", "Delete an index", INDEX_NAME_SCHEMA, _handler("es_delete_index", url)),
            AgentTool("es_list_indices", "List all indices", EMPTY_SCHEMA, _handler("es_list_indices", url)),
            AgentTool("es_cluster_health", "Get cluster health", EMPTY_SCHEMA, _handler("es_cluster_health", url)),
        ]

    def generate_credentials(self, config):
        return {"password": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
