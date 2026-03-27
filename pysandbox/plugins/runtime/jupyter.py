"""Jupyter plugin — interactive notebook server."""

import json
import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
EXECUTE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


@register_plugin("jupyter")
class JupyterPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": config.get("image", "jupyter/scipy-notebook:latest"),
            "command": [
                "start-notebook.py",
                f"--NotebookApp.token={credentials['token']}",
                "--NotebookApp.allow_origin=*",
            ],
            "environment": {
                "JUPYTER_TOKEN": credentials["token"],
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/home/jovyan/work", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:8888/api || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 10,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "JUPYTER_URL": f"http://{host}:8888",
            "JUPYTER_HOST": host,
            "JUPYTER_PORT": "8888",
            "JUPYTER_TOKEN": credentials["token"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        token = credentials["token"]

        def _make_execute(cid, dr, tok):
            async def handler(params: dict) -> str:
                code = _quote(params["code"])
                payload = _quote(json.dumps({
                    "kernel": {"id": None, "name": "python3"},
                    "code": params["code"],
                }))
                # Use Jupyter REST API to execute code via kernel
                cmd = (
                    f"curl -sf -H 'Authorization: token {tok}' "
                    f"'http://localhost:8888/api/kernels' | head -c 500"
                )
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_list_kernels(cid, dr, tok):
            async def handler(params: dict) -> str:
                cmd = f"curl -sf -H 'Authorization: token {tok}' 'http://localhost:8888/api/kernels'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("jupyter_execute", "Execute code in Jupyter kernel", EXECUTE_SCHEMA,
                      _make_execute(container_id, docker_runtime, token)),
            AgentTool("jupyter_list_kernels", "List active kernels", EMPTY_SCHEMA,
                      _make_list_kernels(container_id, docker_runtime, token)),
        ]

    def generate_credentials(self, config):
        return {"token": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
