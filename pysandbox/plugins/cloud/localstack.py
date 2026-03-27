"""LocalStack plugin — full AWS service emulation."""

import secrets
from typing import Any

from pysandbox.agent.tools.s3_tools import (
    DYNAMO_GET_SCHEMA, DYNAMO_PUT_SCHEMA, DYNAMO_QUERY_SCHEMA,
    LAMBDA_INVOKE_SCHEMA, S3_DELETE_SCHEMA, S3_DOWNLOAD_SCHEMA,
    S3_LIST_SCHEMA, S3_PRESIGN_SCHEMA, S3_UPLOAD_SCHEMA,
    SM_GET_SCHEMA, SM_PUT_SCHEMA, SNS_CREATE_SCHEMA, SNS_PUB_SCHEMA,
    SQS_CREATE_SCHEMA, SQS_RECV_SCHEMA, SQS_SEND_SCHEMA,
    make_dynamo_get, make_dynamo_put, make_dynamo_query,
    make_lambda_invoke, make_s3_delete, make_s3_download, make_s3_list,
    make_s3_presign, make_s3_upload, make_sm_get, make_sm_put,
    make_sns_create, make_sns_publish, make_sqs_create, make_sqs_receive,
    make_sqs_send,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("localstack")
class LocalStackPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        services = ",".join(config.get("services", [
            "s3", "sqs", "sns", "lambda", "dynamodb", "secretsmanager", "ses",
        ]))
        return {
            "image": f"localstack/localstack:{version}",
            "environment": {
                "SERVICES": services,
                "DEFAULT_REGION": config.get("region", "us-east-1"),
                "AWS_DEFAULT_REGION": config.get("region", "us-east-1"),
                "DEBUG": "0",
                "LOCALSTACK_ACKNOWLEDGE_ACCOUNT_REQUIREMENT": "1",
            },
            "volumes": {
                f"pysb-{sandbox_id[:8]}-{plugin_name}": {"bind": "/var/lib/localstack", "mode": "rw"},
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -sf http://localhost:4566/_localstack/health || exit 1"],
                "interval": 10_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 60,
                "start_period": 30_000_000_000,
            },
        }

    def get_env_vars(self, plugin_name, dns_zone, credentials, config):
        endpoint = f"http://{plugin_name}.{dns_zone}:4566"
        region = config.get("region", "us-east-1")
        return {
            "AWS_ENDPOINT_URL": endpoint,
            "AWS_ACCESS_KEY_ID": "localstack",
            "AWS_SECRET_ACCESS_KEY": "localstack",
            "AWS_DEFAULT_REGION": region,
            "AWS_REGION": region,
            "S3_ENDPOINT_URL": endpoint,
            "SQS_ENDPOINT_URL": endpoint,
            "SNS_ENDPOINT_URL": endpoint,
            "DYNAMODB_ENDPOINT_URL": endpoint,
        }

    def get_agent_tools(self, plugin_name, dns_zone, credentials, config,
                        container_id="", docker_runtime=None):
        endpoint_url = "http://localhost:4566"
        region = config.get("region", "us-east-1")
        access_key = "localstack"
        secret_key = "localstack"
        args = (container_id, docker_runtime, endpoint_url, access_key, secret_key, region)
        return [
            AgentTool("s3_upload", "Upload to S3", S3_UPLOAD_SCHEMA, make_s3_upload(*args)),
            AgentTool("s3_download", "Download from S3", S3_DOWNLOAD_SCHEMA, make_s3_download(*args)),
            AgentTool("s3_list", "List S3 objects", S3_LIST_SCHEMA, make_s3_list(*args)),
            AgentTool("s3_delete", "Delete S3 object", S3_DELETE_SCHEMA, make_s3_delete(*args)),
            AgentTool("s3_presign", "Generate presigned URL", S3_PRESIGN_SCHEMA, make_s3_presign(*args)),
            AgentTool("sqs_send", "Send SQS message", SQS_SEND_SCHEMA, make_sqs_send(*args)),
            AgentTool("sqs_receive", "Receive SQS messages", SQS_RECV_SCHEMA, make_sqs_receive(*args)),
            AgentTool("sqs_create_queue", "Create SQS queue", SQS_CREATE_SCHEMA, make_sqs_create(*args)),
            AgentTool("sns_publish", "Publish to SNS", SNS_PUB_SCHEMA, make_sns_publish(*args)),
            AgentTool("sns_create_topic", "Create SNS topic", SNS_CREATE_SCHEMA, make_sns_create(*args)),
            AgentTool("lambda_invoke", "Invoke Lambda", LAMBDA_INVOKE_SCHEMA, make_lambda_invoke(*args)),
            AgentTool("dynamodb_put", "PutItem in DynamoDB", DYNAMO_PUT_SCHEMA, make_dynamo_put(*args)),
            AgentTool("dynamodb_get", "GetItem from DynamoDB", DYNAMO_GET_SCHEMA, make_dynamo_get(*args)),
            AgentTool("dynamodb_query", "Query DynamoDB", DYNAMO_QUERY_SCHEMA, make_dynamo_query(*args)),
            AgentTool("secretsmanager_get", "Get a secret", SM_GET_SCHEMA, make_sm_get(*args)),
            AgentTool("secretsmanager_put", "Put a secret", SM_PUT_SCHEMA, make_sm_put(*args)),
        ]

    def generate_credentials(self, config):
        return {}

    def get_init_commands(self, plugin_name, credentials, config):
        cmds = []
        for bucket in config.get("buckets", []):
            cmds.append(f"awslocal s3 mb s3://{bucket}")
        for queue in config.get("queues", []):
            cmds.append(f"awslocal sqs create-queue --queue-name {queue}")
        return cmds
