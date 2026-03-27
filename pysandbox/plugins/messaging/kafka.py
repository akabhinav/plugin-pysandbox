"""Kafka plugin — KRaft mode (no ZooKeeper), Apache Kafka native image."""

import secrets
from typing import Any

from pysandbox.agent.tools.kafka_tools import (
    EMPTY_SCHEMA, GROUP_SCHEMA, KAFKA_CONSUME_SCHEMA, KAFKA_PRODUCE_SCHEMA,
    TOPIC_CREATE_SCHEMA, TOPIC_NAME_SCHEMA, make_kafka_consume,
    make_kafka_create_topic, make_kafka_delete_topic,
    make_kafka_describe_topic, make_kafka_groups, make_kafka_lag,
    make_kafka_list_topics, make_kafka_produce,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("kafka")
class KafkaPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        cluster_id = secrets.token_urlsafe(16)
        return {
            "image": f"apache/kafka:{version}",
            "environment": {
                "KAFKA_NODE_ID": "1",
                "KAFKA_PROCESS_ROLES": "broker,controller",
                "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9093",
                "KAFKA_LISTENERS": "PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093",
                "KAFKA_ADVERTISED_LISTENERS": f"PLAINTEXT://{plugin_name}.{dns_zone}:9092",
                "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT",
                "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
                "KAFKA_INTER_BROKER_LISTENER_NAME": "PLAINTEXT",
                "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
                "KAFKA_LOG_DIRS": "/tmp/kafka-logs",
                "CLUSTER_ID": cluster_id,
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 40,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "KAFKA_BOOTSTRAP_SERVERS": f"{host}:9092",
            "KAFKA_HOST": host,
            "KAFKA_PORT": "9092",
            "KAFKA_USERNAME": credentials.get("username", ""),
            "KAFKA_PASSWORD": credentials.get("password", ""),
            "SPRING_KAFKA_BOOTSTRAP_SERVERS": f"{host}:9092",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        bootstrap = f"localhost:9092"
        return [
            AgentTool("kafka_produce", "Produce a message to a topic", KAFKA_PRODUCE_SCHEMA,
                      make_kafka_produce(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_consume", "Consume N messages from a topic", KAFKA_CONSUME_SCHEMA,
                      make_kafka_consume(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_list_topics", "List all Kafka topics", EMPTY_SCHEMA,
                      make_kafka_list_topics(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_create_topic", "Create a new topic", TOPIC_CREATE_SCHEMA,
                      make_kafka_create_topic(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_describe_topic", "Describe a topic", TOPIC_NAME_SCHEMA,
                      make_kafka_describe_topic(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_delete_topic", "Delete a topic", TOPIC_NAME_SCHEMA,
                      make_kafka_delete_topic(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_consumer_groups", "List consumer groups", EMPTY_SCHEMA,
                      make_kafka_groups(container_id, docker_runtime, bootstrap)),
            AgentTool("kafka_lag", "Get consumer group lag", GROUP_SCHEMA,
                      make_kafka_lag(container_id, docker_runtime, bootstrap)),
        ]

    def generate_credentials(self, config):
        return {
            "username": f"pysb_{secrets.token_hex(4)}",
            "password": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        cmds = []
        for topic in config.get("topics", []):
            name = topic if isinstance(topic, str) else topic["name"]
            parts = topic.get("partitions", 1) if isinstance(topic, dict) else 1
            ret = topic.get("replication", 1) if isinstance(topic, dict) else 1
            cmds.append(
                f"/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 "
                f"--create --if-not-exists --topic {name} "
                f"--partitions {parts} --replication-factor {ret}"
            )
        return cmds
