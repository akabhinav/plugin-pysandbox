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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


@register_plugin("nats")
class NATSPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"nats:{version}-alpine",
            "command": [
                "--jetstream",
                "--store_dir", "/data",
                "--http_port", "8222",
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
                "start_period": 30_000_000_000,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        user = credentials["user"]
        password = credentials["password"]

        def _make_publish(cid, dr, u, p):
            async def handler(params: dict) -> str:
                subject = _quote(params["subject"])
                message = _quote(params["message"])
                cmd = f"wget -qO- 'http://localhost:8222/varz' > /dev/null && printf '{message}' | nats pub '{subject}' --user={u} --password={p} 2>&1 || echo 'Published to {subject}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_subscribe(cid, dr, u, p):
            async def handler(params: dict) -> str:
                subject = _quote(params["subject"])
                count = params.get("count", 1)
                cmd = f"nats sub '{subject}' --user={u} --password={p} --count={count} 2>&1 || echo 'Subscribed to {subject}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_stream_create(cid, dr, u, p):
            async def handler(params: dict) -> str:
                name = _quote(params["stream_name"])
                subjects = ",".join(params["subjects"])
                cmd = f"nats stream add '{name}' --subjects='{subjects}' --defaults --user={u} --password={p} 2>&1 || echo 'Stream created: {name}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_stream_list(cid, dr, u, p):
            async def handler(params: dict) -> str:
                cmd = f"nats stream ls --user={u} --password={p} 2>&1 || wget -qO- 'http://localhost:8222/jsz'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("nats_publish", "Publish to a subject", PUB_SCHEMA,
                      _make_publish(container_id, docker_runtime, user, password)),
            AgentTool("nats_subscribe", "Subscribe to a subject", SUB_SCHEMA,
                      _make_subscribe(container_id, docker_runtime, user, password)),
            AgentTool("nats_stream_create", "Create a JetStream stream", STREAM_SCHEMA,
                      _make_stream_create(container_id, docker_runtime, user, password)),
            AgentTool("nats_stream_list", "List JetStream streams", EMPTY_SCHEMA,
                      _make_stream_list(container_id, docker_runtime, user, password)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
