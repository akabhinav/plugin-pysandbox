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
        assert "spark://" in env["SPARK_MASTER_URL"]
        assert env["SPARK_DEPLOY_MODE"] == "cluster"

    def test_get_docker_config_cluster_mode(self):
        """Spark runs master + workers via spark-class entrypoint."""
        plugin = get_plugin("spark")
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, {}, "3.5.4")

        assert cfg["image"] == "apache/spark:3.5.4"
        assert "healthcheck" in cfg
        assert cfg["command"][0] == "bash"
        assert cfg["command"][1] == "-c"
        script = cfg["command"][2]
        assert "spark-class org.apache.spark.deploy.master.Master" in script
        assert "spark-class org.apache.spark.deploy.worker.Worker" in script

    def test_get_docker_config_default_workers(self):
        """Default is 2 workers with 2 cores each."""
        plugin = get_plugin("spark")
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, {}, "3.5.4")

        env = cfg["environment"]
        assert env["SPARK_WORKERS"] == "2"
        assert env["SPARK_WORKER_CORES"] == "2"
        assert env["SPARK_WORKER_MEMORY"] == "1g"

    def test_get_docker_config_custom_workers(self):
        """Custom worker count and resources."""
        plugin = get_plugin("spark")
        config = {"workers": 4, "worker_cores": 4, "worker_memory": "2g"}
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, config, "3.5.4")

        env = cfg["environment"]
        assert env["SPARK_WORKERS"] == "4"
        assert env["SPARK_WORKER_CORES"] == "4"
        assert env["SPARK_WORKER_MEMORY"] == "2g"
        assert "seq 1 4" in cfg["command"][2]

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

    def test_healthcheck_verifies_alive_workers(self):
        """Healthcheck queries master API to confirm workers are registered."""
        plugin = get_plugin("spark")
        cfg = plugin.get_docker_config("spark", "sb123", "abc.sandbox.local", {}, {}, "3.5.4")

        hc_test = cfg["healthcheck"]["test"][1]
        assert "8080/json/" in hc_test
        assert "aliveworkers" in hc_test
