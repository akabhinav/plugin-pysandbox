"""MySQL plugin — relational database."""

import secrets
from typing import Any

from pysandbox.agent.tools.sql_tools import (
    EMPTY_SCHEMA, SQL_EXECUTE_SCHEMA, SQL_QUERY_SCHEMA, TABLE_NAME_SCHEMA,
    make_mysql_describe_table_handler, make_mysql_execute_handler,
    make_mysql_list_tables_handler, make_mysql_query_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("mysql")
class MySQLPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        # Allow overriding the image, e.g. to use `mariadb:11` as a drop-in
        # replacement in environments where the official `mysql:` image can't
        # be pulled (uses fs features some storage drivers don't support).
        # MariaDB ships the same `mysql`/`mysqladmin` CLI tools, so all agent
        # handlers continue to work unchanged.
        image = config.get("image", f"mysql:{version}")
        return {
            "image": image,
            "environment": {
                "MYSQL_ROOT_PASSWORD": credentials["root_password"],
                "MYSQL_DATABASE": credentials["database"],
                "MYSQL_USER": credentials["user"],
                "MYSQL_PASSWORD": credentials["password"],
                # MariaDB honors MARIADB_* but also accepts MYSQL_*;
                # set both for maximum compatibility.
                "MARIADB_ROOT_PASSWORD": credentials["root_password"],
                "MARIADB_DATABASE": credentials["database"],
                "MARIADB_USER": credentials["user"],
                "MARIADB_PASSWORD": credentials["password"],
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/mysql", "mode": "rw"},
            },
            "healthcheck": {
                # mysqladmin / mariadb-admin ping returns 0 even if the server
                # replies with "access denied", which still proves the daemon
                # is accepting TCP connections. Avoiding --user/--password
                # sidesteps shell-quoting issues when the generated password
                # contains `-` or `=` (common with token_urlsafe). Try both
                # CLI names so the healthcheck works against either the
                # official `mysql:` image or the `mariadb:` drop-in.
                "test": [
                    "CMD-SHELL",
                    "mysqladmin ping --protocol=tcp -h 127.0.0.1 --silent 2>/dev/null "
                    "|| mariadb-admin ping --protocol=tcp -h 127.0.0.1 --silent 2>/dev/null "
                    "|| exit 1",
                ],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 12,
                "start_period": 30_000_000_000,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        user = credentials["user"]
        password = credentials["password"]
        database = credentials["database"]
        return [
            AgentTool("sql_query", "Run a SQL SELECT query", SQL_QUERY_SCHEMA,
                      make_mysql_query_handler(container_id, docker_runtime, user, password, database)),
            AgentTool("sql_execute", "Run INSERT/UPDATE/DELETE/DDL", SQL_EXECUTE_SCHEMA,
                      make_mysql_execute_handler(container_id, docker_runtime, user, password, database)),
            AgentTool("db_list_tables", "List all tables", EMPTY_SCHEMA,
                      make_mysql_list_tables_handler(container_id, docker_runtime, user, password, database)),
            AgentTool("db_describe_table", "Describe table schema", TABLE_NAME_SCHEMA,
                      make_mysql_describe_table_handler(container_id, docker_runtime, user, password, database)),
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
