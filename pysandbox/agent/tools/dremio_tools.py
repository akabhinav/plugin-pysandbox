"""Dremio agent tool handlers — execute SQL and manage sources via REST API."""

from __future__ import annotations

SQL_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "SQL query to execute"},
    },
    "required": ["sql"],
}

SOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Source name"},
        "type": {"type": "string", "description": "Source type (e.g. NAS, S3, PostgreSQL)"},
        "config": {"type": "object", "description": "Source-specific config"},
    },
    "required": ["name", "type"],
}

SOURCE_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Source name"},
    },
    "required": ["name"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}

SPACE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Space name"},
    },
    "required": ["name"],
}

FOLDER_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Full path like 'space.folder'"},
    },
    "required": ["path"],
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def _curl_auth(user: str, password: str) -> str:
    """Build curl command prefix with Dremio auth token retrieval."""
    return (
        f"TOKEN=$(curl -s -X POST http://localhost:9047/apiv2/login "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"userName\":\"{user}\",\"password\":\"{_quote(password)}\"}}' "
        f"| python3 -c \"import sys,json; print(json.load(sys.stdin)['token'])\" 2>/dev/null) && "
    )


def make_dremio_sql_handler(container_id: str, docker_runtime, user: str, password: str):
    """Execute SQL via Dremio REST API."""
    async def handler(params: dict) -> str:
        sql = _quote(params["sql"])
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"JOB=$(curl -s -X POST http://localhost:9047/api/v3/sql "
            f"-H 'Authorization: _dremio$TOKEN' "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"sql\":\"{sql}\"}}' "
            f"| python3 -c \"import sys,json; print(json.load(sys.stdin).get('id',''))\" 2>/dev/null) && "
            f"sleep 2 && "
            f"curl -s http://localhost:9047/api/v3/job/$JOB/results "
            f"-H 'Authorization: _dremio$TOKEN'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dremio_list_sources_handler(container_id: str, docker_runtime, user: str, password: str):
    """List all configured data sources."""
    async def handler(params: dict) -> str:
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"curl -s http://localhost:9047/api/v3/catalog "
            f"-H 'Authorization: _dremio$TOKEN'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dremio_add_source_handler(container_id: str, docker_runtime, user: str, password: str):
    """Add a new data source."""
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        src_type = _quote(params["type"])
        config = params.get("config", {})
        import json
        config_json = _quote(json.dumps(config))
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"curl -s -X POST http://localhost:9047/api/v3/catalog "
            f"-H 'Authorization: _dremio$TOKEN' "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"entityType\":\"source\",\"name\":\"{name}\",\"type\":\"{src_type}\",\"config\":{config_json}}}'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dremio_create_space_handler(container_id: str, docker_runtime, user: str, password: str):
    """Create a new Dremio space."""
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"curl -s -X POST http://localhost:9047/api/v3/catalog "
            f"-H 'Authorization: _dremio$TOKEN' "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"entityType\":\"space\",\"name\":\"{name}\"}}'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dremio_list_spaces_handler(container_id: str, docker_runtime, user: str, password: str):
    """List all spaces."""
    async def handler(params: dict) -> str:
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"curl -s http://localhost:9047/api/v3/catalog "
            f"-H 'Authorization: _dremio$TOKEN' "
            f"| python3 -c \"import sys,json; data=json.load(sys.stdin); "
            f"[print(e['path'][0]) for e in data.get('data',[]) if e.get('containerType')=='SPACE']\""
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dremio_get_source_handler(container_id: str, docker_runtime, user: str, password: str):
    """Get details of a specific source."""
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        auth = _curl_auth(user, password)
        cmd = (
            f"{auth}"
            f"curl -s http://localhost:9047/api/v3/catalog/by-path/{name} "
            f"-H 'Authorization: _dremio$TOKEN'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
