"""Nessie catalog agent tool handlers — manage branches, tags, and tables via REST API."""

from __future__ import annotations

EMPTY_SCHEMA = {"type": "object", "properties": {}}

BRANCH_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Branch name"},
    },
    "required": ["name"],
}

MERGE_SCHEMA = {
    "type": "object",
    "properties": {
        "from_branch": {"type": "string", "description": "Source branch to merge from"},
        "to_branch": {"type": "string", "description": "Target branch (default: main)", "default": "main"},
    },
    "required": ["from_branch"],
}

TABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {"type": "string", "description": "Branch or tag name", "default": "main"},
    },
}

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Tag name"},
        "ref": {"type": "string", "description": "Branch to tag from", "default": "main"},
    },
    "required": ["name"],
}

LOG_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {"type": "string", "description": "Branch or tag name", "default": "main"},
        "limit": {"type": "integer", "description": "Max entries", "default": 20},
    },
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def make_nessie_list_branches(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        cmd = "curl -sf http://localhost:19120/api/v2/trees"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_create_branch(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        cmd = (
            f"MAIN_HASH=$(curl -sf http://localhost:19120/api/v2/trees/main "
            f"| python3 -c \"import sys,json; print(json.load(sys.stdin)['hash'])\") && "
            f"curl -sf -X POST http://localhost:19120/api/v2/trees "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"type\":\"BRANCH\",\"name\":\"{name}\",\"hash\":\"'$MAIN_HASH'\"}}'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_delete_branch(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        cmd = (
            f"HASH=$(curl -sf http://localhost:19120/api/v2/trees/{name} "
            f"| python3 -c \"import sys,json; print(json.load(sys.stdin)['hash'])\") && "
            f"curl -sf -X DELETE 'http://localhost:19120/api/v2/trees/{name}?expected-hash='$HASH"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_list_contents(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        ref = _quote(params.get("ref", "main"))
        cmd = f"curl -sf http://localhost:19120/api/v2/trees/{ref}/entries"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_commit_log(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        ref = _quote(params.get("ref", "main"))
        limit = params.get("limit", 20)
        cmd = f"curl -sf 'http://localhost:19120/api/v2/trees/{ref}/history?maxRecords={limit}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_create_tag(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        name = _quote(params["name"])
        ref = _quote(params.get("ref", "main"))
        cmd = (
            f"REF_HASH=$(curl -sf http://localhost:19120/api/v2/trees/{ref} "
            f"| python3 -c \"import sys,json; print(json.load(sys.stdin)['hash'])\") && "
            f"curl -sf -X POST http://localhost:19120/api/v2/trees "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"type\":\"TAG\",\"name\":\"{name}\",\"hash\":\"'$REF_HASH'\"}}'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_nessie_merge(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        from_branch = _quote(params["from_branch"])
        to_branch = _quote(params.get("to_branch", "main"))
        cmd = (
            f"FROM_HASH=$(curl -sf http://localhost:19120/api/v2/trees/{from_branch} "
            f"| python3 -c \"import sys,json; print(json.load(sys.stdin)['hash'])\") && "
            f"curl -sf -X POST http://localhost:19120/api/v2/trees/{to_branch}/history/merge "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"fromRefName\":\"{from_branch}\",\"fromHash\":\"'$FROM_HASH'\"}}'"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
