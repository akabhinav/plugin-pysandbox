"""Redis agent tool handlers."""

from __future__ import annotations

KEY_SCHEMA = {
    "type": "object",
    "properties": {"key": {"type": "string"}},
    "required": ["key"],
}

KEY_VALUE_TTL_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "value": {"type": "string"},
        "ttl": {"type": "integer", "description": "TTL in seconds (optional)"},
    },
    "required": ["key", "value"],
}

KEYS_SCHEMA = {
    "type": "object",
    "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
    "required": ["keys"],
}

PATTERN_SCHEMA = {
    "type": "object",
    "properties": {"pattern": {"type": "string", "default": "*"}},
}

HASH_KEY_SCHEMA = {
    "type": "object",
    "properties": {"key": {"type": "string"}, "field": {"type": "string"}},
    "required": ["key", "field"],
}

HASH_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "field": {"type": "string"},
        "value": {"type": "string"},
    },
    "required": ["key", "field", "value"],
}

LIST_PUSH_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "values": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["key", "values"],
}

LIST_RANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "start": {"type": "integer", "default": 0},
        "stop": {"type": "integer", "default": -1},
    },
    "required": ["key"],
}

ZSET_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "member": {"type": "string"},
        "score": {"type": "number"},
    },
    "required": ["key", "member", "score"],
}

ZRANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "start": {"type": "integer", "default": 0},
        "stop": {"type": "integer", "default": -1},
    },
    "required": ["key"],
}

PUBSUB_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["channel", "message"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _make_handler(name: str, conn: dict):
    async def handler(params: dict) -> str:
        return f"[{name}] host={conn['host']}:{conn['port']} params={params}"
    return handler


def make_redis_get(conn: dict):
    return _make_handler("redis_get", conn)

def make_redis_set(conn: dict):
    return _make_handler("redis_set", conn)

def make_redis_del(conn: dict):
    return _make_handler("redis_delete", conn)

def make_redis_scan(conn: dict):
    return _make_handler("redis_scan", conn)

def make_redis_hget(conn: dict):
    return _make_handler("redis_hget", conn)

def make_redis_hset(conn: dict):
    return _make_handler("redis_hset", conn)

def make_redis_lpush(conn: dict):
    return _make_handler("redis_lpush", conn)

def make_redis_lrange(conn: dict):
    return _make_handler("redis_lrange", conn)

def make_redis_zadd(conn: dict):
    return _make_handler("redis_zadd", conn)

def make_redis_zrange(conn: dict):
    return _make_handler("redis_zrange", conn)

def make_redis_publish(conn: dict):
    return _make_handler("redis_publish", conn)

def make_redis_flush(conn: dict):
    return _make_handler("redis_flushdb", conn)

def make_redis_info(conn: dict):
    return _make_handler("redis_info", conn)
