"""Tests for the LocalStack plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestLocalStackPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("localstack")

    def test_no_credentials(self):
        """LocalStack uses fixed credentials."""
        plugin = get_plugin("localstack")
        assert plugin.generate_credentials({}) == {}

    def test_get_env_vars(self):
        plugin = get_plugin("localstack")
        env = plugin.get_env_vars("aws", "abc.sandbox.local", {}, {})

        assert env["AWS_ENDPOINT_URL"] == "http://aws.abc.sandbox.local:4566"
        assert env["AWS_ACCESS_KEY_ID"] == "localstack"
        assert env["AWS_DEFAULT_REGION"] == "us-east-1"

    def test_custom_region(self):
        plugin = get_plugin("localstack")
        env = plugin.get_env_vars("aws", "abc.sandbox.local", {}, {"region": "eu-west-1"})
        assert env["AWS_DEFAULT_REGION"] == "eu-west-1"

    def test_get_agent_tools(self):
        """LocalStack provides 16 AWS tools."""
        plugin = get_plugin("localstack")
        tools = plugin.get_agent_tools("aws", "abc.sandbox.local", {}, {})

        assert len(tools) == 16
        names = {t.name for t in tools}
        assert "s3_upload" in names
        assert "sqs_send" in names
        assert "dynamodb_put" in names
        assert "lambda_invoke" in names

    def test_init_commands_create_resources(self):
        plugin = get_plugin("localstack")
        cmds = plugin.get_init_commands("aws", {}, {
            "buckets": ["data", "uploads"],
            "queues": ["orders"],
        })

        assert len(cmds) == 3
        assert "s3 mb s3://data" in cmds[0]
        assert "sqs create-queue" in cmds[2]
