"""Code executor plugin — isolated code execution environment."""

import secrets
from typing import Any

from pysandbox.agent.tools.shell_tools import (
    EMPTY_SCHEMA, FILE_LIST_SCHEMA, FILE_READ_SCHEMA, FILE_WRITE_SCHEMA,
    SHELL_EXEC_SCHEMA,
    make_file_list, make_file_read, make_file_write, make_shell_exec,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("code-executor")
class CodeExecutorPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": config.get("image", f"python:{version}-slim"),
            "command": ["sh", "-c", "tail -f /dev/null"],  # Keep alive
            "environment": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "SANDBOX_ID": sandbox_id,
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/workspace", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "echo ok"],
                "interval": 10_000_000_000,
                "timeout": 2_000_000_000,
                "retries": 3,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "CODE_EXECUTOR_HOST": host,
            "WORKSPACE_PATH": "/workspace",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        return [
            AgentTool("shell_exec", "Execute a shell command", SHELL_EXEC_SCHEMA,
                      make_shell_exec(container_id, docker_runtime)),
            AgentTool("file_read", "Read a file", FILE_READ_SCHEMA,
                      make_file_read(container_id, docker_runtime)),
            AgentTool("file_write", "Write a file", FILE_WRITE_SCHEMA,
                      make_file_write(container_id, docker_runtime)),
            AgentTool("file_list", "List files", FILE_LIST_SCHEMA,
                      make_file_list(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        cmds = []
        for pkg in config.get("pip_packages", []):
            cmds.append(f"pip install {pkg}")
        return cmds
