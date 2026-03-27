"""HashiCorp Vault plugin — secrets management."""

import json
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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


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
                "start_period": 30_000_000_000,
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

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        token = credentials["root_token"]

        def _make_read(cid, dr, tok):
            async def handler(params: dict) -> str:
                path = _quote(params["path"])
                cmd = f"VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN={tok} vault kv get -format=json '{path}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_write(cid, dr, tok):
            async def handler(params: dict) -> str:
                path = _quote(params["path"])
                data_pairs = " ".join(f"{k}={_quote(str(v))}" for k, v in params["data"].items())
                cmd = f"VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN={tok} vault kv put '{path}' {data_pairs}"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_list(cid, dr, tok):
            async def handler(params: dict) -> str:
                path = _quote(params["path"])
                cmd = f"VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN={tok} vault kv list -format=json '{path}'"
                return await dr.exec_in_container(cid, cmd)
            return handler

        def _make_status(cid, dr, tok):
            async def handler(params: dict) -> str:
                cmd = f"VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN={tok} vault status -format=json"
                return await dr.exec_in_container(cid, cmd)
            return handler

        return [
            AgentTool("vault_read", "Read a secret from Vault", SECRET_READ_SCHEMA,
                      _make_read(container_id, docker_runtime, token)),
            AgentTool("vault_write", "Write a secret to Vault", SECRET_WRITE_SCHEMA,
                      _make_write(container_id, docker_runtime, token)),
            AgentTool("vault_list", "List secrets at a path", SECRET_READ_SCHEMA,
                      _make_list(container_id, docker_runtime, token)),
            AgentTool("vault_status", "Get Vault status", EMPTY_SCHEMA,
                      _make_status(container_id, docker_runtime, token)),
        ]

    def generate_credentials(self, config):
        return {"root_token": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return ["vault secrets enable -path=secret kv-v2 || true"]
