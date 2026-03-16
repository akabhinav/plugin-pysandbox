"""MinIO plugin — S3-compatible object storage."""

import secrets
from typing import Any

from pysandbox.agent.tools.s3_tools import (
    S3_DELETE_SCHEMA, S3_DOWNLOAD_SCHEMA, S3_LIST_SCHEMA,
    S3_PRESIGN_SCHEMA, S3_UPLOAD_SCHEMA,
    make_s3_delete, make_s3_download, make_s3_list, make_s3_presign, make_s3_upload,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("minio")
class MinIOPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        return {
            "image": f"minio/minio:{version}",
            "command": ["server", "/data", "--console-address", ":9001"],
            "environment": {
                "MINIO_ROOT_USER": credentials["access_key"],
                "MINIO_ROOT_PASSWORD": credentials["secret_key"],
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/data", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "mc ready local || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 10,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        endpoint = f"http://{host}:9000"
        return {
            "MINIO_ENDPOINT": endpoint,
            "MINIO_HOST": host,
            "MINIO_PORT": "9000",
            "MINIO_CONSOLE_PORT": "9001",
            "MINIO_ACCESS_KEY": credentials["access_key"],
            "MINIO_SECRET_KEY": credentials["secret_key"],
            "S3_ENDPOINT_URL": endpoint,
            "AWS_ACCESS_KEY_ID": credentials["access_key"],
            "AWS_SECRET_ACCESS_KEY": credentials["secret_key"],
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config):
        host = f"{plugin_name}.{dns_zone}"
        cfg = {
            "endpoint_url": f"http://{host}:9000",
            "aws_access_key_id": credentials["access_key"],
            "aws_secret_access_key": credentials["secret_key"],
        }
        return [
            AgentTool("s3_upload", "Upload to S3/MinIO", S3_UPLOAD_SCHEMA, make_s3_upload(cfg)),
            AgentTool("s3_download", "Download from S3/MinIO", S3_DOWNLOAD_SCHEMA, make_s3_download(cfg)),
            AgentTool("s3_list", "List objects", S3_LIST_SCHEMA, make_s3_list(cfg)),
            AgentTool("s3_delete", "Delete object", S3_DELETE_SCHEMA, make_s3_delete(cfg)),
            AgentTool("s3_presign", "Generate presigned URL", S3_PRESIGN_SCHEMA, make_s3_presign(cfg)),
        ]

    def generate_credentials(self, config):
        return {
            "access_key": f"pysb{secrets.token_hex(8)}",
            "secret_key": secrets.token_urlsafe(32),
        }

    def get_init_commands(self, plugin_name, credentials, config):
        cmds = []
        for bucket in config.get("buckets", []):
            cmds.append(f"mc mb local/{bucket} --ignore-existing")
        return cmds
