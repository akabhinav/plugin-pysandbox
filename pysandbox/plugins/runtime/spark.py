"""Apache Spark plugin — standalone cluster mode (master + workers) with Iceberg + Nessie + S3."""

from typing import Any

from pysandbox.agent.tools.spark_tools import (
    EMPTY_SCHEMA,
    PYSPARK_SCHEMA,
    SPARK_SQL_SCHEMA,
    SPARK_SUBMIT_SCHEMA,
    make_pyspark_handler,
    make_spark_list_apps_handler,
    make_spark_show_tables_handler,
    make_spark_sql_handler,
    make_spark_submit_handler,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("spark")
class SparkPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        nessie_host = config.get("nessie_host", f"nessie.{dns_zone}")
        minio_host = config.get("minio_host", f"minio.{dns_zone}")
        s3_access_key = config.get("s3_access_key", "minioadmin")
        s3_secret_key = config.get("s3_secret_key", "minioadmin")
        warehouse = config.get("warehouse", "s3a://warehouse/")
        workers = config.get("workers", 2)
        worker_cores = config.get("worker_cores", 2)
        worker_memory = config.get("worker_memory", "1g")

        # Entrypoint script: start master, then N workers, then wait
        start_script = (
            "#!/bin/bash\n"
            "set -e\n"
            "export SPARK_HOME=/opt/spark\n"
            "export SPARK_MASTER_HOST=0.0.0.0\n"
            "export SPARK_LOG_DIR=/opt/spark/logs\n"
            "mkdir -p $SPARK_LOG_DIR\n"
            "\n"
            "# Start Spark Master\n"
            "$SPARK_HOME/sbin/start-master.sh\n"
            "echo 'Waiting for master to start...'\n"
            "for i in $(seq 1 30); do\n"
            "  curl -sf http://localhost:8080/ > /dev/null 2>&1 && break\n"
            "  sleep 1\n"
            "done\n"
            "\n"
            f"# Start {workers} Spark Worker(s)\n"
            f"for i in $(seq 1 {workers}); do\n"
            f"  SPARK_WORKER_CORES={worker_cores} SPARK_WORKER_MEMORY={worker_memory} "
            "$SPARK_HOME/sbin/start-worker.sh spark://localhost:7077\n"
            "  echo \"Worker $i started\"\n"
            "done\n"
            "\n"
            "echo 'Spark cluster ready: master + workers'\n"
            "# Keep container alive by tailing logs\n"
            "tail -f $SPARK_LOG_DIR/*.out\n"
        )

        return {
            "image": f"apache/spark:{version}",
            "command": ["bash", "-c", start_script],
            "environment": {
                "SPARK_HOME": "/opt/spark",
                "SPARK_MASTER_HOST": "0.0.0.0",
                "SPARK_NO_DAEMONIZE": "false",
                # Lakehouse config
                "NESSIE_URI": f"http://{nessie_host}:19120/api/v1",
                "S3_ENDPOINT": f"http://{minio_host}:9000",
                "S3_ACCESS_KEY": s3_access_key,
                "S3_SECRET_KEY": s3_secret_key,
                "WAREHOUSE": warehouse,
                # Cluster info
                "SPARK_WORKERS": str(workers),
                "SPARK_WORKER_CORES": str(worker_cores),
                "SPARK_WORKER_MEMORY": worker_memory,
            },
            "healthcheck": {
                "test": ["CMD-SHELL",
                         "curl -sf http://localhost:8080/ && "
                         "curl -sf http://localhost:8081/ || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 30,
                "start_period": 45_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        return {
            "SPARK_MASTER_URL": f"spark://{host}:7077",
            "SPARK_MASTER_UI": f"http://{host}:8080",
            "SPARK_HOST": host,
            "SPARK_MASTER_PORT": "7077",
            "SPARK_UI_PORT": "8080",
            "SPARK_DEPLOY_MODE": "cluster",
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        nessie_host = config.get("nessie_host", f"nessie.{dns_zone}")
        minio_host = config.get("minio_host", f"minio.{dns_zone}")
        nessie_uri = f"http://{nessie_host}:19120/api/v1"
        s3_endpoint = f"http://{minio_host}:9000"
        s3_access_key = config.get("s3_access_key", "minioadmin")
        s3_secret_key = config.get("s3_secret_key", "minioadmin")
        warehouse = config.get("warehouse", "s3a://warehouse/")

        tool_args = (container_id, docker_runtime,
                     nessie_uri, s3_endpoint, s3_access_key, s3_secret_key, warehouse)
        return [
            AgentTool("spark_sql", "Execute Spark SQL with Iceberg/Nessie on cluster", SPARK_SQL_SCHEMA,
                      make_spark_sql_handler(*tool_args)),
            AgentTool("spark_submit", "Submit a Spark job to the cluster", SPARK_SUBMIT_SCHEMA,
                      make_spark_submit_handler(*tool_args)),
            AgentTool("pyspark_run", "Run inline PySpark code on cluster", PYSPARK_SCHEMA,
                      make_pyspark_handler(*tool_args)),
            AgentTool("spark_show_tables", "Show Iceberg tables in Nessie catalog", EMPTY_SCHEMA,
                      make_spark_show_tables_handler(*tool_args)),
            AgentTool("spark_list_apps", "List running Spark applications and workers", EMPTY_SCHEMA,
                      make_spark_list_apps_handler(container_id, docker_runtime)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        return []
