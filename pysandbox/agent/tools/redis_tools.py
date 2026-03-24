"""Redis agent tool handlers — execute real commands via docker exec."""

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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def _auth_flag(password: str | None) -> str:
    if password:
        return f"-a '{_quote(password)}' --no-auth-warning"
    return ""


def make_redis_get(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        cmd = f"redis-cli {auth} GET '{_quote(params['key'])}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_set(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        value = _quote(params["value"])
        ttl = params.get("ttl")
        if ttl:
            cmd = f"redis-cli {auth} SET '{key}' '{value}' EX {int(ttl)}"
        else:
            cmd = f"redis-cli {auth} SET '{key}' '{value}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_del(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        cmd = f"redis-cli {auth} DEL '{key}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_scan(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        pattern = _quote(params.get("pattern", "*"))
        cmd = f"redis-cli {auth} --scan --pattern '{pattern}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_hget(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        field = _quote(params["field"])
        cmd = f"redis-cli {auth} HGET '{key}' '{field}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_hset(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        field = _quote(params["field"])
        value = _quote(params["value"])
        cmd = f"redis-cli {auth} HSET '{key}' '{field}' '{value}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_lpush(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        values = " ".join(f"'{_quote(v)}'" for v in params["values"])
        cmd = f"redis-cli {auth} LPUSH '{key}' {values}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_lrange(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        start = params.get("start", 0)
        stop = params.get("stop", -1)
        cmd = f"redis-cli {auth} LRANGE '{key}' {start} {stop}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_zadd(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        score = params["score"]
        member = _quote(params["member"])
        cmd = f"redis-cli {auth} ZADD '{key}' {score} '{member}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_zrange(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        key = _quote(params["key"])
        start = params.get("start", 0)
        stop = params.get("stop", -1)
        cmd = f"redis-cli {auth} ZRANGE '{key}' {start} {stop} WITHSCORES"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_publish(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        channel = _quote(params["channel"])
        message = _quote(params["message"])
        cmd = f"redis-cli {auth} PUBLISH '{channel}' '{message}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_flush(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        cmd = f"redis-cli {auth} FLUSHDB"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_redis_info(container_id: str, docker_runtime, password: str | None = None):
    async def handler(params: dict) -> str:
        auth = _auth_flag(password)
        cmd = f"redis-cli {auth} INFO"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
