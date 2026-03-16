"""Redis plugin — in-memory data store, cache, and message broker."""

import secrets
from typing import Any

from pysandbox.agent.tools.redis_tools import (
    EMPTY_SCHEMA, HASH_FIELD_SCHEMA, HASH_KEY_SCHEMA, KEY_SCHEMA,
    KEY_VALUE_TTL_SCHEMA, KEYS_SCHEMA, LIST_PUSH_SCHEMA, LIST_RANGE_SCHEMA,
    PATTERN_SCHEMA, PUBSUB_SCHEMA, ZRANGE_SCHEMA, ZSET_SCHEMA,
    make_redis_del, make_redis_flush, make_redis_get, make_redis_hget,
    make_redis_hset, make_redis_info, make_redis_lpush, make_redis_lrange,
    make_redis_publish, make_redis_scan, make_redis_set, make_redis_zadd,
    make_redis_zrange,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("redis")
class RedisPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        maxmem = config.get("maxmemory", "256mb")
        policy = config.get("maxmemory_policy", "allkeys-lru")
        return {
            "image": f"redis:{version}-alpine",
            "command": [
                "redis-server",
                "--requirepass", credentials["password"],
                "--maxmemory", maxmem,
                "--maxmemory-policy", policy,
                "--appendonly", "yes",
                "--save", "60 1",
            ],
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD", "redis-cli", "-a", credentials["password"], "ping"],
                "interval": 5_000_000_000,
                "timeout": 2_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        url = f"redis://:{credentials['password']}@{host}:6379/0"
        return {
            "REDIS_URL": url,
            "REDIS_HOST": host,
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": credentials["password"],
            "CELERY_BROKER_URL": url,
            "CELERY_RESULT_BACKEND": url,
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        conn = {"host": f"{plugin_name}.{dns_zone}", "port": 6379, "password": credentials["password"]}
        return [
            AgentTool("redis_get", "GET a Redis key", KEY_SCHEMA, make_redis_get(conn)),
            AgentTool("redis_set", "SET a Redis key with optional TTL", KEY_VALUE_TTL_SCHEMA, make_redis_set(conn)),
            AgentTool("redis_delete", "DEL one or more Redis keys", KEYS_SCHEMA, make_redis_del(conn)),
            AgentTool("redis_scan", "SCAN keys matching a pattern", PATTERN_SCHEMA, make_redis_scan(conn)),
            AgentTool("redis_hget", "HGET from a Redis hash", HASH_KEY_SCHEMA, make_redis_hget(conn)),
            AgentTool("redis_hset", "HSET in a Redis hash", HASH_FIELD_SCHEMA, make_redis_hset(conn)),
            AgentTool("redis_lpush", "LPUSH to a Redis list", LIST_PUSH_SCHEMA, make_redis_lpush(conn)),
            AgentTool("redis_lrange", "LRANGE from a Redis list", LIST_RANGE_SCHEMA, make_redis_lrange(conn)),
            AgentTool("redis_zadd", "ZADD to a sorted set", ZSET_SCHEMA, make_redis_zadd(conn)),
            AgentTool("redis_zrange", "ZRANGE from a sorted set", ZRANGE_SCHEMA, make_redis_zrange(conn)),
            AgentTool("redis_publish", "PUBLISH to a channel", PUBSUB_SCHEMA, make_redis_publish(conn)),
            AgentTool("redis_flushdb", "FLUSHDB (clear all keys)", EMPTY_SCHEMA, make_redis_flush(conn)),
            AgentTool("redis_info", "Get Redis server INFO", EMPTY_SCHEMA, make_redis_info(conn)),
        ]

    def generate_credentials(self, config):
        return {"password": secrets.token_urlsafe(32)}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
