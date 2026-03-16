"""SQLite plugin — lightweight file-based database (no separate container)."""

import secrets
from typing import Any

from pysandbox.agent.tools.sql_tools import (
    EMPTY_SCHEMA, SQL_EXECUTE_SCHEMA, SQL_QUERY_SCHEMA, TABLE_NAME_SCHEMA,
    make_describe_table_handler, make_list_tables_handler,
    make_sql_execute_handler, make_sql_query_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("sqlite")
class SQLitePlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        # SQLite uses a lightweight alpine container with sqlite3 installed
        db_path = config.get("db_path", "/data/sandbox.db")
        return {
            "image": "alpine:latest",
            "command": ["sh", "-c", f"apk add --no-cache sqlite && tail -f /dev/null"],
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "sqlite3 /data/sandbox.db 'SELECT 1'"],
                "interval": 5_000_000_000,
                "timeout": 2_000_000_000,
                "retries": 5,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        db_path = config.get("db_path", "/data/sandbox.db")
        return {
            "SQLITE_PATH": db_path,
            "DATABASE_URL": f"sqlite:///{db_path}",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        db_path = config.get("db_path", "/data/sandbox.db")
        url = f"sqlite:///{db_path}"
        return [
            AgentTool("sql_query", "Run a SQL SELECT", SQL_QUERY_SCHEMA, make_sql_query_handler(url)),
            AgentTool("sql_execute", "Run SQL write", SQL_EXECUTE_SCHEMA, make_sql_execute_handler(url)),
            AgentTool("db_list_tables", "List tables", EMPTY_SCHEMA, make_list_tables_handler(url)),
            AgentTool("db_describe_table", "Describe table", TABLE_NAME_SCHEMA, make_describe_table_handler(url)),
        ]

    def generate_credentials(self, config):
        return {}  # SQLite needs no credentials

    def get_init_commands(self, plugin_name, credentials, config):
        return []
