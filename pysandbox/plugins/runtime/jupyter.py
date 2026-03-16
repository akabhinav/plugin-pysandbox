"""Jupyter plugin — interactive notebook server."""

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


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = f"http://{plugin_name}.{dns_zone}:8888"
        return [
            AgentTool("jupyter_execute", "Execute code in Jupyter kernel", EXECUTE_SCHEMA, _handler("jupyter_execute", url)),
            AgentTool("jupyter_list_kernels", "List active kernels", EMPTY_SCHEMA, _handler("jupyter_list_kernels", url)),
        ]

    def generate_credentials(self, config):
        return {"token": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
