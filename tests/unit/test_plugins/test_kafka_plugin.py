"""Tests for the Kafka plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestKafkaPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("kafka")

    def test_generate_credentials(self):
        plugin = get_plugin("kafka")
        creds = plugin.generate_credentials({})
        assert "username" in creds
        assert "password" in creds

    def test_get_env_vars(self):
        plugin = get_plugin("kafka")
        creds = {"username": "u", "password": "p"}
        env = plugin.get_env_vars("my-kafka", "abc.sandbox.local", creds, {})

        assert env["KAFKA_BOOTSTRAP_SERVERS"] == "my-kafka.abc.sandbox.local:9092"
        assert env["KAFKA_HOST"] == "my-kafka.abc.sandbox.local"

    def test_get_docker_config_kraft(self):
        """Kafka uses Confluent Local image (KRaft mode, no ZooKeeper)."""
        plugin = get_plugin("kafka")
        creds = {"username": "u", "password": "p"}
        cfg = plugin.get_docker_config("kafka", "sb123", "abc.sandbox.local", creds, {}, "latest")

        assert cfg["image"] == "confluentinc/confluent-local:latest"
        assert "KAFKA_ADVERTISED_LISTENERS" in cfg["environment"]

    def test_get_agent_tools(self):
        plugin = get_plugin("kafka")
        creds = {"username": "u", "password": "p"}
        tools = plugin.get_agent_tools("kafka", "abc.sandbox.local", creds, {})

        assert len(tools) == 8
        names = {t.name for t in tools}
        assert "kafka_produce" in names
        assert "kafka_consume" in names
        assert "kafka_create_topic" in names

    def test_init_commands_create_topics(self):
        plugin = get_plugin("kafka")
        creds = {"username": "u", "password": "p"}
        cmds = plugin.get_init_commands("kafka", creds, {"topics": ["events", "orders"]})

        assert len(cmds) == 2
        assert "events" in cmds[0]
        assert "orders" in cmds[1]
