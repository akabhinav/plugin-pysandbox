"""HashiCorp Vault plugin — secrets management."""

import secrets
from typing import Any

from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin

EMPTY_SCHEMA = {"type": "object", "properties": {}}
SECRET_READ_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}
SECRET_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "data": {"type": "object"},
    },
    "required": ["path", "data"],
}


def _handler(name, addr):
    async def h(params):
        return f"[{name}] addr={addr} params={params}"
    return h


@register_plugin("vault")
class VaultPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"hashicorp/vault:{version}",
            "command": ["server", "-dev", f"-dev-root-token-id={credentials['root_token']}"],
            "environment": {
                "VAULT_DEV_ROOT_TOKEN_ID": credentials["root_token"],
                "VAULT_DEV_LISTEN_ADDRESS": "0.0.0.0:8200",
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "vault status"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "VAULT_ADDR": f"http://{host}:8200",
            "VAULT_TOKEN": credentials["root_token"],
            "VAULT_HOST": host,
            "VAULT_PORT": "8200",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        addr = f"http://{plugin_name}.{dns_zone}:8200"
        return [
            AgentTool("vault_read", "Read a secret from Vault", SECRET_READ_SCHEMA, _handler("vault_read", addr)),
            AgentTool("vault_write", "Write a secret to Vault", SECRET_WRITE_SCHEMA, _handler("vault_write", addr)),
            AgentTool("vault_list", "List secrets at a path", SECRET_READ_SCHEMA, _handler("vault_list", addr)),
            AgentTool("vault_status", "Get Vault status", EMPTY_SCHEMA, _handler("vault_status", addr)),
        ]

    def generate_credentials(self, config):
        return {"root_token": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return ["vault secrets enable -path=secret kv-v2 || true"]
