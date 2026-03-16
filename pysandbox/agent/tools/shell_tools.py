"""Shell and file agent tool handlers."""

from __future__ import annotations

SHELL_EXEC_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Shell command to execute"},
        "timeout": {"type": "integer", "default": 60, "description": "Timeout in seconds"},
    },
    "required": ["command"],
}

FILE_READ_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}

FILE_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
}

FILE_LIST_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "default": "."}},
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def make_shell_exec(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        return await docker_runtime.exec_in_container(container_id, params["command"])
    return handler


def make_file_read(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        return await docker_runtime.exec_in_container(container_id, f"cat {params['path']}")
    return handler


def make_file_write(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        # Use printf to avoid shell injection via heredoc
        escaped = params["content"].replace("'", "'\\''")
        cmd = f"printf '%s' '{escaped}' > {params['path']}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_file_list(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        path = params.get("path", ".")
        return await docker_runtime.exec_in_container(container_id, f"ls -la {path}")
    return handler
