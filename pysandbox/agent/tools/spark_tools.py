"""Spark agent tool handlers — submit jobs, run SQL, and manage via spark-submit/spark-sql."""

from __future__ import annotations

SPARK_SQL_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "Spark SQL query to execute"},
    },
    "required": ["sql"],
}

SPARK_SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "app": {"type": "string", "description": "Path to .py or .jar file to submit"},
        "args": {"type": "string", "description": "Application arguments", "default": ""},
        "packages": {"type": "string", "description": "Comma-separated Maven packages", "default": ""},
    },
    "required": ["app"],
}

PYSPARK_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "Python code to execute in PySpark"},
    },
    "required": ["code"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def _iceberg_conf(nessie_uri: str, s3_endpoint: str, s3_access_key: str, s3_secret_key: str, warehouse: str) -> str:
    """Build Spark Iceberg + Nessie + S3 config flags."""
    confs = [
        "--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "--conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog",
        "--conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog",
        f"--conf spark.sql.catalog.nessie.uri={nessie_uri}",
        "--conf spark.sql.catalog.nessie.ref=main",
        f"--conf spark.sql.catalog.nessie.warehouse={warehouse}",
        "--conf spark.sql.catalog.nessie.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
        f"--conf spark.sql.catalog.nessie.s3.endpoint={s3_endpoint}",
        "--conf spark.sql.catalog.nessie.s3.path-style-access=true",
        f"--conf spark.hadoop.fs.s3a.endpoint={s3_endpoint}",
        f"--conf spark.hadoop.fs.s3a.access.key={s3_access_key}",
        f"--conf spark.hadoop.fs.s3a.secret.key={s3_secret_key}",
        "--conf spark.hadoop.fs.s3a.path.style.access=true",
        "--conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem",
    ]
    return " ".join(confs)


def _iceberg_packages() -> str:
    """Maven packages for Iceberg + Nessie + AWS/S3."""
    return (
        "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,"
        "org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.99.0,"
        "software.amazon.awssdk:bundle:2.29.38,"
        "software.amazon.awssdk:url-connection-client:2.29.38"
    )


def make_spark_sql_handler(container_id: str, docker_runtime,
                           nessie_uri: str, s3_endpoint: str,
                           s3_access_key: str, s3_secret_key: str, warehouse: str):
    """Execute Spark SQL with Iceberg/Nessie catalog pre-configured."""
    async def handler(params: dict) -> str:
        sql = _quote(params["sql"])
        conf = _iceberg_conf(nessie_uri, s3_endpoint, s3_access_key, s3_secret_key, warehouse)
        pkgs = _iceberg_packages()
        cmd = (
            f"/opt/spark/bin/spark-sql --master local[*] "
            f"--packages {pkgs} "
            f"{conf} "
            f"-e \"{sql}\""
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_spark_submit_handler(container_id: str, docker_runtime,
                              nessie_uri: str, s3_endpoint: str,
                              s3_access_key: str, s3_secret_key: str, warehouse: str):
    """Submit a Spark job."""
    async def handler(params: dict) -> str:
        app = _quote(params["app"])
        args = params.get("args", "")
        extra_packages = params.get("packages", "")
        conf = _iceberg_conf(nessie_uri, s3_endpoint, s3_access_key, s3_secret_key, warehouse)
        pkgs = _iceberg_packages()
        if extra_packages:
            pkgs = f"{pkgs},{extra_packages}"
        cmd = (
            f"/opt/spark/bin/spark-submit --master local[*] "
            f"--packages {pkgs} "
            f"{conf} "
            f"{app} {args}"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_pyspark_handler(container_id: str, docker_runtime,
                         nessie_uri: str, s3_endpoint: str,
                         s3_access_key: str, s3_secret_key: str, warehouse: str):
    """Run PySpark code inline."""
    async def handler(params: dict) -> str:
        code = _quote(params["code"])
        conf = _iceberg_conf(nessie_uri, s3_endpoint, s3_access_key, s3_secret_key, warehouse)
        pkgs = _iceberg_packages()
        cmd = (
            f"/opt/spark/bin/spark-submit --master local[*] "
            f"--packages {pkgs} "
            f"{conf} "
            f"/dev/stdin <<'PYEOF'\n{code}\nPYEOF"
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_spark_list_apps_handler(container_id: str, docker_runtime):
    """List running Spark applications."""
    async def handler(params: dict) -> str:
        cmd = "curl -sf http://localhost:8080/json/ 2>/dev/null || echo '{\"status\":\"master not running in standalone mode\"}'"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_spark_show_tables_handler(container_id: str, docker_runtime,
                                   nessie_uri: str, s3_endpoint: str,
                                   s3_access_key: str, s3_secret_key: str, warehouse: str):
    """Show all Iceberg tables in the Nessie catalog."""
    async def handler(params: dict) -> str:
        conf = _iceberg_conf(nessie_uri, s3_endpoint, s3_access_key, s3_secret_key, warehouse)
        pkgs = _iceberg_packages()
        cmd = (
            f"/opt/spark/bin/spark-sql --master local[*] "
            f"--packages {pkgs} "
            f"{conf} "
            f"-e \"SHOW NAMESPACES IN nessie; SHOW TABLES IN nessie;\""
        )
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
