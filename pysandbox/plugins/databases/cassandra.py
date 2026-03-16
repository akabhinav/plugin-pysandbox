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


def _handler(name, host):
    async def h(params):
        return f"[{name}] host={host} params={params}"
    return h


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
                "retries": 12,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return [
            AgentTool("cql_query", "Run a CQL SELECT query", CQL_SCHEMA, _handler("cql_query", host)),
            AgentTool("cql_execute", "Run a CQL write statement", CQL_SCHEMA, _handler("cql_execute", host)),
            AgentTool("cassandra_keyspaces", "List keyspaces", EMPTY_SCHEMA, _handler("cassandra_keyspaces", host)),
            AgentTool("cassandra_tables", "List tables in keyspace", KEYSPACE_SCHEMA, _handler("cassandra_tables", host)),
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
