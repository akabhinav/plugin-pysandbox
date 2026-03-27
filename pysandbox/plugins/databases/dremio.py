"""Dremio plugin — data lakehouse platform with unified SQL analytics."""

import secrets
from typing import Any

from pysandbox.agent.tools.dremio_tools import (
    EMPTY_SCHEMA,
    FOLDER_SCHEMA,
    SOURCE_NAME_SCHEMA,
    SOURCE_SCHEMA,
    SPACE_SCHEMA,
    SQL_QUERY_SCHEMA,
    make_dremio_add_source_handler,
    make_dremio_create_space_handler,
    make_dremio_get_source_handler,
    make_dremio_list_sources_handler,
    make_dremio_list_spaces_handler,
    make_dremio_sql_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("dremio")
class DremioPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"dremio/dremio-oss:{version}",
            "environment": {
                "DREMIO_JAVA_SERVER_EXTRA_OPTS": "-Dpaths.dist=file:///opt/dremio/data/dist",
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {
                    "bind": "/opt/dremio/data", "mode": "rw",
                },
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:9047 || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 40,
                "start_period": 60_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "DREMIO_URL": f"http://{host}:9047",
            "DREMIO_HOST": host,
            "DREMIO_PORT": "9047",
            "DREMIO_ODBC_PORT": "31010",
            "DREMIO_FLIGHT_PORT": "45678",
            "DREMIO_USER": credentials["user"],
            "DREMIO_PASSWORD": credentials["password"],
            "DREMIO_JDBC_URL": f"jdbc:dremio:direct={host}:31010",
            "DREMIO_ARROW_FLIGHT_URI": f"grpc://{host}:45678",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        user = credentials["user"]
        password = credentials["password"]
        return [
            AgentTool("dremio_sql", "Execute a SQL query on Dremio", SQL_QUERY_SCHEMA,
                      make_dremio_sql_handler(container_id, docker_runtime, user, password)),
            AgentTool("dremio_list_sources", "List all data sources", EMPTY_SCHEMA,
                      make_dremio_list_sources_handler(container_id, docker_runtime, user, password)),
            AgentTool("dremio_add_source", "Add a new data source", SOURCE_SCHEMA,
                      make_dremio_add_source_handler(container_id, docker_runtime, user, password)),
            AgentTool("dremio_get_source", "Get details of a data source", SOURCE_NAME_SCHEMA,
                      make_dremio_get_source_handler(container_id, docker_runtime, user, password)),
            AgentTool("dremio_create_space", "Create a Dremio space", SPACE_SCHEMA,
                      make_dremio_create_space_handler(container_id, docker_runtime, user, password)),
            AgentTool("dremio_list_spaces", "List all spaces", EMPTY_SCHEMA,
                      make_dremio_list_spaces_handler(container_id, docker_runtime, user, password)),
        ]

    def generate_credentials(self, config):
        return {
            "user": config.get("admin_user", "dremio"),
            "password": config.get("admin_password", secrets.token_urlsafe(16)),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        # Dremio first-time setup: bootstrap admin user via REST API
        user = credentials["user"]
        password = credentials["password"]
        return [
            (
                f"curl -s -X PUT http://localhost:9047/apiv2/bootstrap/firstuser "
                f"-H 'Content-Type: application/json' "
                f"-d '{{\"userName\":\"{user}\",\"firstName\":\"Admin\",\"lastName\":\"User\","
                f"\"email\":\"{user}@sandbox.local\",\"createdAt\":0,"
                f"\"password\":\"{password}\"}}' || true"
            ),
        ]
