"""Kafka agent tool handlers."""

from __future__ import annotations

KAFKA_PRODUCE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "message": {"type": "string"},
        "key": {"type": "string"},
    },
    "required": ["topic", "message"],
}

KAFKA_CONSUME_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "count": {"type": "integer", "default": 10},
        "timeout_ms": {"type": "integer", "default": 5000},
    },
    "required": ["topic"],
}

TOPIC_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "partitions": {"type": "integer", "default": 1},
        "replication_factor": {"type": "integer", "default": 1},
    },
    "required": ["topic"],
}

TOPIC_NAME_SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string"}},
    "required": ["topic"],
}

GROUP_SCHEMA = {
    "type": "object",
    "properties": {"group_id": {"type": "string"}},
    "required": ["group_id"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _make_handler(name: str, bootstrap: str, auth: dict):
    async def handler(params: dict) -> str:
        return f"[{name}] bootstrap={bootstrap} params={params}"
    return handler


def make_kafka_produce(bootstrap: str, auth: dict):
    return _make_handler("kafka_produce", bootstrap, auth)

def make_kafka_consume(bootstrap: str, auth: dict):
    return _make_handler("kafka_consume", bootstrap, auth)

def make_kafka_list_topics(bootstrap: str, auth: dict):
    return _make_handler("kafka_list_topics", bootstrap, auth)

def make_kafka_create_topic(bootstrap: str, auth: dict):
    return _make_handler("kafka_create_topic", bootstrap, auth)

def make_kafka_describe_topic(bootstrap: str, auth: dict):
    return _make_handler("kafka_describe_topic", bootstrap, auth)

def make_kafka_delete_topic(bootstrap: str, auth: dict):
    return _make_handler("kafka_delete_topic", bootstrap, auth)

def make_kafka_groups(bootstrap: str, auth: dict):
    return _make_handler("kafka_consumer_groups", bootstrap, auth)

def make_kafka_lag(bootstrap: str, auth: dict):
    return _make_handler("kafka_lag", bootstrap, auth)
