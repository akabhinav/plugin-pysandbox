"""RabbitMQ plugin — message broker with management UI."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
PUBLISH_SCHEMA = {
    "type": "object",
    "properties": {
        "exchange": {"type": "string", "default": ""},
        "routing_key": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["routing_key", "message"],
}
CONSUME_SCHEMA = {
    "type": "object",
    "properties": {
        "queue": {"type": "string"},
        "count": {"type": "integer", "default": 1},
    },
    "required": ["queue"],
}
QUEUE_SCHEMA = {
    "type": "object",
    "properties": {"queue": {"type": "string"}},
    "required": ["queue"],
}


def _handler(name, host):
    async def h(params):
        return f"[{name}] host={host} params={params}"
    return h


@register_plugin("rabbitmq")
class RabbitMQPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"rabbitmq:{version}-management-alpine",
            "environment": {
                "RABBITMQ_DEFAULT_USER": credentials["user"],
                "RABBITMQ_DEFAULT_PASS": credentials["password"],
                "RABBITMQ_DEFAULT_VHOST": credentials.get("vhost", "/"),
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/rabbitmq", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "rabbitmq-diagnostics -q ping"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        amqp_url = f"amqp://{credentials['user']}:{credentials['password']}@{host}:5672/"
        return {
            "RABBITMQ_URL": amqp_url,
            "RABBITMQ_HOST": host,
            "RABBITMQ_PORT": "5672",
            "RABBITMQ_MANAGEMENT_PORT": "15672",
            "RABBITMQ_USER": credentials["user"],
            "RABBITMQ_PASSWORD": credentials["password"],
            "AMQP_URL": amqp_url,
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return [
            AgentTool("rabbitmq_publish", "Publish a message", PUBLISH_SCHEMA, _handler("rabbitmq_publish", host)),
            AgentTool("rabbitmq_consume", "Consume messages from queue", CONSUME_SCHEMA, _handler("rabbitmq_consume", host)),
            AgentTool("rabbitmq_create_queue", "Declare a queue", QUEUE_SCHEMA, _handler("rabbitmq_create_queue", host)),
            AgentTool("rabbitmq_list_queues", "List all queues", EMPTY_SCHEMA, _handler("rabbitmq_list_queues", host)),
            AgentTool("rabbitmq_delete_queue", "Delete a queue", QUEUE_SCHEMA, _handler("rabbitmq_delete_queue", host)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "vhost": config.get("vhost", "/"),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
