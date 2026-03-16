"""PostgreSQL plugin — relational database with full SQL support."""

import secrets
from typing import Any

from pysandbox.agent.tools.sql_tools import (
    DUMP_SCHEMA,
    EMPTY_SCHEMA,
    SQL_EXECUTE_SCHEMA,
    SQL_EXPLAIN_SCHEMA,
    SQL_MIGRATE_SCHEMA,
    SQL_QUERY_SCHEMA,
    TABLE_NAME_SCHEMA,
    make_describe_table_handler,
    make_dump_handler,
    make_list_indexes_handler,
    make_list_tables_handler,
    make_sql_execute_handler,
    make_sql_explain_handler,
    make_sql_migrate_handler,
    make_sql_query_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("postgres")
class PostgresPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"postgres:{version}",
            "environment": {
                "POSTGRES_DB": credentials["database"],
                "POSTGRES_USER": credentials["user"],
                "POSTGRES_PASSWORD": credentials["password"],
                "POSTGRES_INITDB_ARGS": "--encoding=UTF-8",
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {
                    "bind": "/var/lib/postgresql/data", "mode": "rw",
                },
            },
            "command": [
                "postgres",
                "-c", "max_connections=200",
                "-c", f"shared_buffers={config.get('shared_buffers', '128MB')}",
                "-c", "log_min_duration_statement=1000",
            ],
            "healthcheck": {
                "test": ["CMD-SHELL", f"pg_isready -U {credentials['user']} -d {credentials['database']}"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        url = f"postgresql://{credentials['user']}:{credentials['password']}@{host}:5432/{credentials['database']}"
        return {
            "POSTGRES_URL": url,
            "POSTGRES_HOST": host,
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": credentials["database"],
            "POSTGRES_USER": credentials["user"],
            "POSTGRES_PASSWORD": credentials["password"],
            "DATABASE_URL": url,
            "SQLALCHEMY_DATABASE_URI": url,
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = self.get_env_vars(plugin_name, dns_zone, credentials, config)["POSTGRES_URL"]
        return [
            AgentTool("sql_query", "Run a SQL SELECT query", SQL_QUERY_SCHEMA, make_sql_query_handler(url)),
            AgentTool("sql_execute", "Run INSERT/UPDATE/DELETE/DDL", SQL_EXECUTE_SCHEMA, make_sql_execute_handler(url)),
            AgentTool("sql_migrate", "Run a SQL migration", SQL_MIGRATE_SCHEMA, make_sql_migrate_handler(url)),
            AgentTool("sql_explain", "EXPLAIN ANALYZE a query", SQL_EXPLAIN_SCHEMA, make_sql_explain_handler(url)),
            AgentTool("db_list_tables", "List all tables", EMPTY_SCHEMA, make_list_tables_handler(url)),
            AgentTool("db_describe_table", "Describe table schema", TABLE_NAME_SCHEMA, make_describe_table_handler(url)),
            AgentTool("db_list_indexes", "List indexes on a table", TABLE_NAME_SCHEMA, make_list_indexes_handler(url)),
            AgentTool("db_dump", "pg_dump the database", DUMP_SCHEMA, make_dump_handler(url)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "database": config.get("db", "sandbox_db"),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        cmds = []
        for ext in config.get("extensions", ["uuid-ossp", "pgcrypto"]):
            cmds.append(
                f"psql -U {credentials['user']} -d {credentials['database']} "
                f"-c 'CREATE EXTENSION IF NOT EXISTS \"{ext}\"'"
            )
        return cmds
