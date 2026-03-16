"""Docker-in-Docker agent tool handlers."""

from __future__ import annotations

DOCKER_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "image": {"type": "string"},
        "command": {"type": "string"},
    },
    "required": ["image"],
}

DOCKER_BUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "dockerfile_path": {"type": "string"},
        "tag": {"type": "string"},
    },
    "required": ["dockerfile_path", "tag"],
}

DOCKER_PS_SCHEMA = {"type": "object", "properties": {}}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def make_docker_run(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        cmd = f"docker run --rm {params['image']} {params.get('command', '')}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_docker_build(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        cmd = f"docker build -t {params['tag']} -f {params['dockerfile_path']} ."
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_docker_ps(container_id: str, docker_runtime):
    async def handler(params: dict) -> str:
        return await docker_runtime.exec_in_container(container_id, "docker ps")
    return handler
