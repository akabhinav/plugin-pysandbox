"""Tests for the Apache Spark plugin."""

import pytest

from pysandbox.plugin.registry import get_plugin, is_registered


class TestSparkPlugin:
    @pytest.fixture(autouse=True)
    def _load_plugins(self):
        from pysandbox.plugin.loader import discover_and_load_all
        discover_and_load_all()

    def test_registered(self):
        assert is_registered("spark")

    def test_generate_credentials_empty(self):
        plugin = get_plugin("spark")
        creds = plugin.generate_credentials({})
        assert creds == {}

    def test_get_env_vars(self):
        plugin = get_plugin("spark")
        env = plugin.get_env_vars("spark", "abc.sandbox.local", {}, {})

        assert env["SPARK_HOST"] == "spark.abc.sandbox.local"
        assert env["SPARK_MASTER_PORT"] == "7077"
        assert env["SPARK_UI_PORT"] == "8080"
        assert "SPARK_MASTER_URL" in env
        assert "spark://" in env["SPARK_MASTER_URL"]

    def test_get_docker_config(self):
        plugin = get_plugin("spark")
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, {}, "3.5.4")

        assert cfg["image"] == "apache/spark:3.5.4"
        assert "healthcheck" in cfg
        assert "org.apache.spark.deploy.master.Master" in cfg["command"]

    def test_get_docker_config_with_lakehouse(self):
        """Spark config includes Nessie and MinIO when configured."""
        plugin = get_plugin("spark")
        config = {
            "nessie_host": "nessie.abc.sandbox.local",
            "minio_host": "minio.abc.sandbox.local",
            "s3_access_key": "mykey",
            "s3_secret_key": "mysecret",
            "warehouse": "s3a://lakehouse/",
        }
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, config, "3.5.4")

        env = cfg["environment"]
        assert "nessie.abc.sandbox.local" in env["NESSIE_URI"]
        assert "minio.abc.sandbox.local" in env["S3_ENDPOINT"]
        assert env["S3_ACCESS_KEY"] == "mykey"
        assert env["WAREHOUSE"] == "s3a://lakehouse/"

    def test_get_agent_tools(self):
        plugin = get_plugin("spark")
        tools = plugin.get_agent_tools("spark", "abc.sandbox.local", {}, {})

        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "spark_sql" in names
        assert "spark_submit" in names
        assert "pyspark_run" in names
        assert "spark_show_tables" in names
        assert "spark_list_apps" in names

    def test_init_commands_empty(self):
        plugin = get_plugin("spark")
        cmds = plugin.get_init_commands("spark", {}, {})
        assert cmds == []
