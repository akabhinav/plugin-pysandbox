"""NATS plugin — lightweight high-performance messaging."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
PUB_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["subject", "message"],
}
SUB_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "count": {"type": "integer", "default": 1},
    },
    "required": ["subject"],
}
STREAM_SCHEMA = {
    "type": "object",
    "properties": {
        "stream_name": {"type": "string"},
        "subjects": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stream_name", "subjects"],
}


def _handler(name, url):
    async def h(params):
        return f"[{name}] url={url} params={params}"
    return h


@register_plugin("nats")
class NATSPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"nats:{version}-alpine",
            "command": [
                "--jetstream",
                "--store_dir", "/data",
                "--user", credentials["user"],
                "--pass", credentials["password"],
            ],
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "wget -qO- http://localhost:8222/healthz || exit 1"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        url = f"nats://{credentials['user']}:{credentials['password']}@{host}:4222"
        return {
            "NATS_URL": url,
            "NATS_HOST": host,
            "NATS_PORT": "4222",
            "NATS_MONITOR_PORT": "8222",
            "NATS_USER": credentials["user"],
            "NATS_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        url = self.get_env_vars(plugin_name, dns_zone, credentials, config)["NATS_URL"]
        return [
            AgentTool("nats_publish", "Publish to a subject", PUB_SCHEMA, _handler("nats_publish", url)),
            AgentTool("nats_subscribe", "Subscribe to a subject", SUB_SCHEMA, _handler("nats_subscribe", url)),
            AgentTool("nats_stream_create", "Create a JetStream stream", STREAM_SCHEMA, _handler("nats_stream_create", url)),
            AgentTool("nats_stream_list", "List JetStream streams", EMPTY_SCHEMA, _handler("nats_stream_list", url)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
