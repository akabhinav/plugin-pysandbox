"""Neo4j plugin — graph database."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
CYPHER_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


@register_plugin("neo4j")
class Neo4jPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"neo4j:{version}",
            "environment": {
                "NEO4J_AUTH": f"{credentials['user']}/{credentials['password']}",
                "NEO4J_PLUGINS": '["apoc"]',
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "cypher-shell -u neo4j -p $NEO4J_AUTH 'RETURN 1' || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 12,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "NEO4J_URI": f"bolt://{host}:7687",
            "NEO4J_HOST": host,
            "NEO4J_BOLT_PORT": "7687",
            "NEO4J_HTTP_PORT": "7474",
            "NEO4J_USER": credentials["user"],
            "NEO4J_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        user = credentials["user"]
        password = credentials["password"]

        def _make_cypher_query(cid, dr, u, p):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"cypher-shell -u {u} -p {p} '{query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_cypher_execute(cid, dr, u, p):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"cypher-shell -u {u} -p {p} '{query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_schema(cid, dr, u, p):
            async def handler(params: dict) -> str:
                cmd = f"cypher-shell -u {u} -p {p} 'CALL db.schema.visualization()'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("cypher_query", "Run a Cypher query", CYPHER_SCHEMA,
                      _make_cypher_query(container_id, docker_runtime, user, password)),
            AgentTool("cypher_execute", "Run a Cypher write query", CYPHER_SCHEMA,
                      _make_cypher_execute(container_id, docker_runtime, user, password)),
            AgentTool("neo4j_schema", "Get database schema", EMPTY_SCHEMA,
                      _make_schema(container_id, docker_runtime, user, password)),
        ]

    def generate_credentials(self, config):
        return {
            "user": "neo4j",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
