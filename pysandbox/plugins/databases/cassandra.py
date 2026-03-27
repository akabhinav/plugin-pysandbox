"""Cassandra plugin — distributed wide-column store."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
CQL_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
KEYSPACE_SCHEMA = {
    "type": "object",
    "properties": {"keyspace": {"type": "string"}},
    "required": ["keyspace"],
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


@register_plugin("cassandra")
class CassandraPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"cassandra:{version}",
            "environment": {
                "CASSANDRA_CLUSTER_NAME": config.get("cluster_name", "pysb-cluster"),
                "CASSANDRA_DC": "dc1",
                "CASSANDRA_ENDPOINT_SNITCH": "SimpleSnitch",
                "MAX_HEAP_SIZE": config.get("max_heap", "512M"),
                "HEAP_NEWSIZE": config.get("heap_newsize", "128M"),
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/cassandra", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "nodetool status | grep -q '^UN'"],
                "interval": 15_000_000_000,
                "timeout": 10_000_000_000,
                "retries": 40,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "CASSANDRA_HOST": host,
            "CASSANDRA_PORT": "9042",
            "CASSANDRA_USER": credentials["user"],
            "CASSANDRA_PASSWORD": credentials["password"],
            "CASSANDRA_KEYSPACE": credentials.get("keyspace", "sandbox"),
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        def _make_cql_query(cid, dr):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"cqlsh -e '{query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_cql_execute(cid, dr):
            async def handler(params: dict) -> str:
                query = _quote(params["query"])
                cmd = f"cqlsh -e '{query}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_keyspaces(cid, dr):
            async def handler(params: dict) -> str:
                cmd = "cqlsh -e 'DESCRIBE KEYSPACES;'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_tables(cid, dr):
            async def handler(params: dict) -> str:
                ks = _quote(params["keyspace"])
                cmd = f"cqlsh -e 'USE {ks}; DESCRIBE TABLES;'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("cql_query", "Run a CQL SELECT query", CQL_SCHEMA,
                      _make_cql_query(container_id, docker_runtime)),
            AgentTool("cql_execute", "Run a CQL write statement", CQL_SCHEMA,
                      _make_cql_execute(container_id, docker_runtime)),
            AgentTool("cassandra_keyspaces", "List keyspaces", EMPTY_SCHEMA,
                      _make_keyspaces(container_id, docker_runtime)),
            AgentTool("cassandra_tables", "List tables in keyspace", KEYSPACE_SCHEMA,
                      _make_tables(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {
            "user": "cassandra",
            "password": secrets.token_urlsafe(32),
            "keyspace": config.get("keyspace", "sandbox"),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        ks = credentials.get("keyspace", "sandbox")
        return [
            f"cqlsh -e \"CREATE KEYSPACE IF NOT EXISTS {ks} WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}\"",
        ]
