"""Nessie plugin — Git-like catalog for Apache Iceberg data lakehouses."""

from typing import Any

from pysandbox.agent.tools.nessie_tools import (
    BRANCH_SCHEMA,
    EMPTY_SCHEMA,
    LOG_SCHEMA,
    MERGE_SCHEMA,
    TABLE_SCHEMA,
    TAG_SCHEMA,
    make_nessie_commit_log,
    make_nessie_create_branch,
    make_nessie_create_tag,
    make_nessie_delete_branch,
    make_nessie_list_branches,
    make_nessie_list_contents,
    make_nessie_merge,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("nessie")
class NessiePlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"ghcr.io/projectnessie/nessie:{version}",
            "environment": {
                "NESSIE_VERSION_STORE_TYPE": "IN_MEMORY",
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:19120/api/v2/config || exit 1"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 20,
                "start_period": 15_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "NESSIE_URI": f"http://{host}:19120/api/v2",
            "NESSIE_HOST": host,
            "NESSIE_PORT": "19120",
            "NESSIE_CATALOG_URI": f"http://{host}:19120/api/v1",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        return [
            AgentTool("nessie_list_branches", "List all Nessie branches", EMPTY_SCHEMA,
                      make_nessie_list_branches(container_id, docker_runtime)),
            AgentTool("nessie_create_branch", "Create a new branch", BRANCH_SCHEMA,
                      make_nessie_create_branch(container_id, docker_runtime)),
            AgentTool("nessie_delete_branch", "Delete a branch", BRANCH_SCHEMA,
                      make_nessie_delete_branch(container_id, docker_runtime)),
            AgentTool("nessie_list_contents", "List tables/views on a branch", TABLE_SCHEMA,
                      make_nessie_list_contents(container_id, docker_runtime)),
            AgentTool("nessie_commit_log", "View commit history", LOG_SCHEMA,
                      make_nessie_commit_log(container_id, docker_runtime)),
            AgentTool("nessie_create_tag", "Create a tag from a branch", TAG_SCHEMA,
                      make_nessie_create_tag(container_id, docker_runtime)),
            AgentTool("nessie_merge", "Merge one branch into another", MERGE_SCHEMA,
                      make_nessie_merge(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
