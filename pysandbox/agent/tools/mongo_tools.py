"""MongoDB agent tool handlers — execute real commands via docker exec (mongosh)."""

from __future__ import annotations

import json

MONGO_FIND_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "filter": {"type": "object", "default": {}},
        "limit": {"type": "integer", "default": 20},
    },
    "required": ["collection"],
}

MONGO_INSERT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "document": {"type": "object"},
    },
    "required": ["collection", "document"],
}

MONGO_INSERT_MANY_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "documents": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["collection", "documents"],
}

MONGO_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "filter": {"type": "object"},
        "update": {"type": "object"},
    },
    "required": ["collection", "filter", "update"],
}

MONGO_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "filter": {"type": "object"},
    },
    "required": ["collection", "filter"],
}

MONGO_AGG_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "pipeline": {"type": "array"},
    },
    "required": ["collection", "pipeline"],
}

MONGO_IDX_SCHEMA = {
    "type": "object",
    "properties": {
        "collection": {"type": "string"},
        "keys": {"type": "object"},
    },
    "required": ["collection", "keys"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def _mongosh_cmd(user: str, password: str, database: str, js: str) -> str:
    auth = f"-u {user} -p {password} --authenticationDatabase admin" if user else ""
    escaped_js = _quote(js)
    return f"mongosh {auth} {database} --quiet --eval '{escaped_js}'"


def make_mongo_find(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        filt = json.dumps(params.get("filter", {}))
        limit = params.get("limit", 20)
        js = f"db.{collection}.find({filt}).limit({limit}).toArray()"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_insert_one(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        doc = json.dumps(params["document"])
        js = f"db.{collection}.insertOne({doc})"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_insert_many(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        docs = json.dumps(params["documents"])
        js = f"db.{collection}.insertMany({docs})"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_update(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        filt = json.dumps(params["filter"])
        update = json.dumps(params["update"])
        js = f"db.{collection}.updateMany({filt}, {update})"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_delete(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        filt = json.dumps(params["filter"])
        js = f"db.{collection}.deleteMany({filt})"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_aggregate(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        pipeline = json.dumps(params["pipeline"])
        js = f"db.{collection}.aggregate({pipeline}).toArray()"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_list_collections(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        js = "db.getCollectionNames()"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_mongo_create_index(container_id: str, docker_runtime, user: str, password: str, database: str):
    async def handler(params: dict) -> str:
        collection = params["collection"]
        keys = json.dumps(params["keys"])
        js = f"db.{collection}.createIndex({keys})"
        cmd = _mongosh_cmd(user, password, database, js)
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
