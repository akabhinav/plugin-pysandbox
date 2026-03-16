"""MongoDB plugin — document database."""

import secrets
from typing import Any

from pysandbox.agent.tools.mongo_tools import (
    EMPTY_SCHEMA, MONGO_AGG_SCHEMA, MONGO_DELETE_SCHEMA, MONGO_FIND_SCHEMA,
    MONGO_IDX_SCHEMA, MONGO_INSERT_MANY_SCHEMA, MONGO_INSERT_SCHEMA,
    MONGO_UPDATE_SCHEMA, make_mongo_aggregate, make_mongo_create_index,
    make_mongo_delete, make_mongo_find, make_mongo_insert_many,
    make_mongo_insert_one, make_mongo_list_collections, make_mongo_update,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("mongodb")
class MongoDBPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"mongo:{version}",
            "environment": {
                "MONGO_INITDB_ROOT_USERNAME": credentials["user"],
                "MONGO_INITDB_ROOT_PASSWORD": credentials["password"],
                "MONGO_INITDB_DATABASE": credentials["database"],
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data/db", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "mongosh --eval 'db.adminCommand({ping: 1})' --quiet"],
                "interval": 5_000_000_000,
                "timeout": 3_000_000_000,
                "retries": 12,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        uri = (
            f"mongodb://{credentials['user']}:{credentials['password']}"
            f"@{host}:27017/{credentials['database']}?authSource=admin"
        )
        return {
            "MONGODB_URI": uri,
            "MONGODB_HOST": host,
            "MONGODB_PORT": "27017",
            "MONGODB_DB": credentials["database"],
            "MONGODB_USER": credentials["user"],
            "MONGODB_PASSWORD": credentials["password"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        uri = self.get_env_vars(plugin_name, dns_zone, credentials, config)["MONGODB_URI"]
        db = credentials["database"]
        return [
            AgentTool("mongo_find", "Find documents", MONGO_FIND_SCHEMA, make_mongo_find(uri, db)),
            AgentTool("mongo_insert_one", "Insert a document", MONGO_INSERT_SCHEMA, make_mongo_insert_one(uri, db)),
            AgentTool("mongo_insert_many", "Insert multiple documents", MONGO_INSERT_MANY_SCHEMA, make_mongo_insert_many(uri, db)),
            AgentTool("mongo_update", "Update documents", MONGO_UPDATE_SCHEMA, make_mongo_update(uri, db)),
            AgentTool("mongo_delete", "Delete documents", MONGO_DELETE_SCHEMA, make_mongo_delete(uri, db)),
            AgentTool("mongo_aggregate", "Run aggregation pipeline", MONGO_AGG_SCHEMA, make_mongo_aggregate(uri, db)),
            AgentTool("mongo_list_collections", "List collections", EMPTY_SCHEMA, make_mongo_list_collections(uri, db)),
            AgentTool("mongo_create_index", "Create an index", MONGO_IDX_SCHEMA, make_mongo_create_index(uri, db)),
        ]

    def generate_credentials(self, config):
        return {
            "user": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
            "database": config.get("db", "sandbox_db"),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        return []
