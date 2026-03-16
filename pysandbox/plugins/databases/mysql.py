"""MySQL plugin — relational database."""

import secrets
from typing import Any

from pysandbox.agent.tools.sql_tools import (
    EMPTY_SCHEMA, SQL_EXECUTE_SCHEMA, SQL_QUERY_SCHEMA, TABLE_NAME_SCHEMA,
    make_describe_table_handler, make_list_tables_handler,
    make_sql_execute_handler, make_sql_query_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("mysql")
class MySQLPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"mysql:{version}",
            "environment": {
                "MYSQL_ROOT_PASSWORD": credentials["root_password"],
                "MYSQL_DATABASE": credentials["database"],
                "MYSQL_USER": credentials["user"],
                "MYSQL_PASSWORD": credentials["password"],
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/mysql", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", f"mysqladmin ping -u{credentials['user']} -p{credentials['password']}"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 12,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        url = f"mysql://{credentials['user']}:{credentials['password']}@{host}:3306/{credentials['database']}"
        return {
            "MYSQL_URL": url,
            "MYSQL_HOST": host,
            "MYSQL_PORT": "3306",
            "MYSQL_DATABASE": credentials["database"],
            "MYSQL_USER": credentials["user"],
            "MYSQL_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = self.get_env_vars(plugin_name, dns_zone, credentials, config)["MYSQL_URL"]
        return [
            AgentTool("sql_query", "Run a SQL SELECT query", SQL_QUERY_SCHEMA, make_sql_query_handler(url)),
            AgentTool("sql_execute", "Run INSERT/UPDATE/DELETE/DDL", SQL_EXECUTE_SCHEMA, make_sql_execute_handler(url)),
            AgentTool("db_list_tables", "List all tables", EMPTY_SCHEMA, make_list_tables_handler(url)),
            AgentTool("db_describe_table", "Describe table schema", TABLE_NAME_SCHEMA, make_describe_table_handler(url)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "root_password": secrets.token_urlsafe(32),
            "database": config.get("db", "sandbox_db"),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
