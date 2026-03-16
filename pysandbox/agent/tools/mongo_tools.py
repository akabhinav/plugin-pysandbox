"""MongoDB agent tool handlers."""

from __future__ import annotations

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


def _make_handler(name: str, uri: str, db: str):
    async def handler(params: dict) -> str:
        return f"[{name}] db={db} params={params}"
    return handler


def make_mongo_find(uri: str, db: str): return _make_handler("mongo_find", uri, db)
def make_mongo_insert_one(uri: str, db: str): return _make_handler("mongo_insert_one", uri, db)
def make_mongo_insert_many(uri: str, db: str): return _make_handler("mongo_insert_many", uri, db)
def make_mongo_update(uri: str, db: str): return _make_handler("mongo_update", uri, db)
def make_mongo_delete(uri: str, db: str): return _make_handler("mongo_delete", uri, db)
def make_mongo_aggregate(uri: str, db: str): return _make_handler("mongo_aggregate", uri, db)
def make_mongo_list_collections(uri: str, db: str): return _make_handler("mongo_list_collections", uri, db)
def make_mongo_create_index(uri: str, db: str): return _make_handler("mongo_create_index", uri, db)
