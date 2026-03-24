"""SQL agent tool handlers — execute real queries via docker exec."""

from __future__ import annotations

import json
import shlex

# JSON schemas for tool parameters
SQL_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "SQL SELECT query to run"},
    },
    "required": ["query"],
}

SQL_EXECUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "statement": {"type": "string", "description": "SQL statement (INSERT/UPDATE/DELETE/DDL)"},
    },
    "required": ["statement"],
}

SQL_EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "SQL query to EXPLAIN ANALYZE"},
    },
    "required": ["query"],
}

SQL_MIGRATE_SCHEMA = {
    "type": "object",
    "properties": {
        "migration_sql": {"type": "string", "description": "SQL migration to execute"},
    },
    "required": ["migration_sql"],
}

TABLE_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "table": {"type": "string", "description": "Table name"},
    },
    "required": ["table"],
}

DUMP_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string", "description": "Output file path for the dump"},
    },
    "required": ["output_path"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _quote(s: str) -> str:
    """Shell-safe quoting for SQL strings."""
    return s.replace("'", "'\\''")


# --- PostgreSQL handlers ---

def make_pg_query_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        query = _quote(params["query"])
        cmd = f"psql -U {user} -d {database} -t -A -c '{query}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_execute_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        stmt = _quote(params["statement"])
        cmd = f"psql -U {user} -d {database} -c '{stmt}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_explain_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        query = _quote(params["query"])
        cmd = f"psql -U {user} -d {database} -c 'EXPLAIN ANALYZE {query}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_migrate_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        sql = _quote(params["migration_sql"])
        cmd = f"psql -U {user} -d {database} -c '{sql}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_list_tables_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        cmd = f"psql -U {user} -d {database} -c '\\dt'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_describe_table_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        table = _quote(params["table"])
        cmd = f"psql -U {user} -d {database} -c '\\d {table}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_list_indexes_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        table = _quote(params.get("table", ""))
        if table:
            cmd = f"psql -U {user} -d {database} -c '\\di {table}*'"
        else:
            cmd = f"psql -U {user} -d {database} -c '\\di'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pg_dump_handler(container_id: str, docker_runtime, user: str, database: str):
    async def handler(params: dict) -> str:
        path = params.get("output_path", "/tmp/dump.sql")
        cmd = f"pg_dump -U {user} -d {database} > {shlex.quote(path)}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- MySQL handlers ---

def make_mysql_query_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        query = _quote(params["query"])
        cmd = f"mysql -u {user} -p{password} -D {database} -e '{query}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mysql_execute_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        stmt = _quote(params["statement"])
        cmd = f"mysql -u {user} -p{password} -D {database} -e '{stmt}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mysql_list_tables_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        cmd = f"mysql -u {user} -p{password} -D {database} -e 'SHOW TABLES;'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mysql_describe_table_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        table = _quote(params["table"])
        cmd = f"mysql -u {user} -p{password} -D {database} -e 'DESCRIBE {table};'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- ClickHouse handlers ---

def make_ch_query_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        query = _quote(params["query"])
        cmd = f"clickhouse-client --user {user} --password {password} --database {database} --query '{query}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_ch_execute_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        stmt = _quote(params["statement"])
        cmd = f"clickhouse-client --user {user} --password {password} --database {database} --query '{stmt}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_ch_list_tables_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        cmd = f"clickhouse-client --user {user} --password {password} --database {database} --query 'SHOW TABLES'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_ch_describe_table_handler(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        table = _quote(params["table"])
        cmd = f"clickhouse-client --user {user} --password {password} --database {database} --query 'DESCRIBE TABLE {table}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- SQLite handlers ---

def make_sqlite_query_handler(container_id: str, docker_runtime, db_path: str):
    async def handler(params: dict) -> str:
        query = _quote(params["query"])
        cmd = f"sqlite3 {db_path} '{query}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sqlite_execute_handler(container_id: str, docker_runtime, db_path: str):
    async def handler(params: dict) -> str:
        stmt = _quote(params["statement"])
        cmd = f"sqlite3 {db_path} '{stmt}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sqlite_list_tables_handler(container_id: str, docker_runtime, db_path: str):
    async def handler(params: dict) -> str:
        cmd = f"sqlite3 {db_path} '.tables'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sqlite_describe_table_handler(container_id: str, docker_runtime, db_path: str):
    async def handler(params: dict) -> str:
        table = _quote(params["table"])
        cmd = f"sqlite3 {db_path} '.schema {table}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
