"""Kafka agent tool handlers — execute real commands via docker exec."""

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


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def make_kafka_produce(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        topic = params["topic"]
        message = _quote(params["message"])
        key = params.get("key")
        if key:
            cmd = f"echo '{_quote(key)}:{message}' | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server {bootstrap} --topic {topic} --property parse.key=true --property key.separator=:"
        else:
            cmd = f"echo '{message}' | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server {bootstrap} --topic {topic}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_consume(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        topic = params["topic"]
        count = params.get("count", 10)
        timeout = params.get("timeout_ms", 5000)
        cmd = f"/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server {bootstrap} --topic {topic} --from-beginning --max-messages {count} --timeout-ms {timeout}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_list_topics(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        cmd = f"/opt/kafka/bin/kafka-topics.sh --bootstrap-server {bootstrap} --list"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_create_topic(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        topic = params["topic"]
        partitions = params.get("partitions", 1)
        rf = params.get("replication_factor", 1)
        cmd = f"/opt/kafka/bin/kafka-topics.sh --bootstrap-server {bootstrap} --create --topic {topic} --partitions {partitions} --replication-factor {rf}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_describe_topic(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        topic = params["topic"]
        cmd = f"/opt/kafka/bin/kafka-topics.sh --bootstrap-server {bootstrap} --describe --topic {topic}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_delete_topic(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        topic = params["topic"]
        cmd = f"/opt/kafka/bin/kafka-topics.sh --bootstrap-server {bootstrap} --delete --topic {topic}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_groups(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        cmd = f"/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server {bootstrap} --list"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_kafka_lag(container_id: str, docker_runtime, bootstrap: str):
    async def handler(params: dict) -> str:
        group_id = params["group_id"]
        cmd = f"/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server {bootstrap} --describe --group {group_id}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
