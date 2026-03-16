"""Docker-in-Docker plugin — run Docker inside the sandbox."""

import secrets
from typing import Any

from pysandbox.agent.tools.docker_tools import (
    DOCKER_BUILD_SCHEMA, DOCKER_PS_SCHEMA, DOCKER_RUN_SCHEMA, EMPTY_SCHEMA,
    make_docker_build, make_docker_ps, make_docker_run,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("docker-daemon")
class DockerDaemonPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"docker:{version}-dind",
            "command": ["dockerd", "--host=tcp://0.0.0.0:2376"],
            "environment": {
                "DOCKER_TLS_CERTDIR": "",  # Disable TLS for sandbox-internal use
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/docker", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "docker info || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "DOCKER_HOST": f"tcp://{host}:2376",
            "DOCKER_DAEMON_HOST": host,
            "DOCKER_DAEMON_PORT": "2376",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        # Tools use exec into the DinD container
        return [
            AgentTool("docker_run", "Run a Docker container", DOCKER_RUN_SCHEMA, _placeholder("docker_run")),
            AgentTool("docker_build", "Build a Docker image", DOCKER_BUILD_SCHEMA, _placeholder("docker_build")),
            AgentTool("docker_ps", "List running containers", EMPTY_SCHEMA, _placeholder("docker_ps")),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []


def _placeholder(name):
    async def handler(params):
        return f"[{name}] params={params}"
    return handler
