"""Elasticsearch plugin — search and analytics engine."""

import json
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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


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
                "retries": 40,
                "start_period": 30_000_000_000,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        password = credentials["password"]
        auth = f"-u elastic:{password}"

        def _make_search(cid, dr, auth_flag):
            async def handler(params: dict) -> str:
                index = params["index"]
                query = _quote(json.dumps(params["query"]))
                cmd = f"curl -sf {auth_flag} -H 'Content-Type: application/json' 'http://localhost:9200/{index}/_search' -d '{query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_index_doc(cid, dr, auth_flag):
            async def handler(params: dict) -> str:
                index = params["index"]
                doc = _quote(json.dumps(params["document"]))
                cmd = f"curl -sf {auth_flag} -H 'Content-Type: application/json' -X POST 'http://localhost:9200/{index}/_doc' -d '{doc}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_delete_index(cid, dr, auth_flag):
            async def handler(params: dict) -> str:
                index = params["index"]
                cmd = f"curl -sf {auth_flag} -X DELETE 'http://localhost:9200/{index}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_list_indices(cid, dr, auth_flag):
            async def handler(params: dict) -> str:
                cmd = f"curl -sf {auth_flag} 'http://localhost:9200/_cat/indices?v'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_cluster_health(cid, dr, auth_flag):
            async def handler(params: dict) -> str:
                cmd = f"curl -sf {auth_flag} 'http://localhost:9200/_cluster/health?pretty'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("es_search", "Search documents", SEARCH_SCHEMA,
                      _make_search(container_id, docker_runtime, auth)),
            AgentTool("es_index", "Index a document", INDEX_DOC_SCHEMA,
                      _make_index_doc(container_id, docker_runtime, auth)),
            AgentTool("es_delete_index", "Delete an index", INDEX_NAME_SCHEMA,
                      _make_delete_index(container_id, docker_runtime, auth)),
            AgentTool("es_list_indices", "List all indices", EMPTY_SCHEMA,
                      _make_list_indices(container_id, docker_runtime, auth)),
            AgentTool("es_cluster_health", "Get cluster health", EMPTY_SCHEMA,
                      _make_cluster_health(container_id, docker_runtime, auth)),
        ]

    def generate_credentials(self, config):
        return {"password": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
