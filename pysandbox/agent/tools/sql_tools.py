"""SQL agent tool handlers for database plugins."""

from __future__ import annotations

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


def make_sql_query_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[sql_query] Would execute SELECT on {url}: {params.get('query', '')}"
    return handler


def make_sql_execute_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[sql_execute] Would execute on {url}: {params.get('statement', '')}"
    return handler


def make_sql_explain_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[sql_explain] Would EXPLAIN ANALYZE on {url}: {params.get('query', '')}"
    return handler


def make_sql_migrate_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[sql_migrate] Would run migration on {url}"
    return handler


def make_list_tables_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[db_list_tables] Would list tables on {url}"
    return handler


def make_describe_table_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[db_describe_table] Would describe {params.get('table', '')} on {url}"
    return handler


def make_list_indexes_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[db_list_indexes] Would list indexes for {params.get('table', '')} on {url}"
    return handler


def make_dump_handler(url: str):
    async def handler(params: dict) -> str:
        return f"[db_dump] Would dump database to {params.get('output_path', '')}"
    return handler
