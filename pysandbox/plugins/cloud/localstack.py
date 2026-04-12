"""LocalStack plugin — full AWS service emulation."""

import secrets
from typing import Any

from pysandbox.agent.tools.s3_tools import (
    APIGW_LIST_SCHEMA, CFN_LIST_SCHEMA, CW_LIST_METRICS_SCHEMA, CW_PUT_METRIC_SCHEMA,
    DYNAMO_GET_SCHEMA, DYNAMO_PUT_SCHEMA, DYNAMO_QUERY_SCHEMA,
    EVENTS_LIST_BUSES_SCHEMA, EVENTS_LIST_RULES_SCHEMA, EVENTS_PUT_SCHEMA,
    IAM_CREATE_USER_SCHEMA, IAM_LIST_ROLES_SCHEMA, IAM_LIST_USERS_SCHEMA,
    KINESIS_CREATE_SCHEMA, KINESIS_LIST_SCHEMA, KINESIS_PUT_SCHEMA,
    LAMBDA_INVOKE_SCHEMA, R53_LIST_SCHEMA, S3_DELETE_SCHEMA, S3_DOWNLOAD_SCHEMA,
    S3_LIST_BUCKETS_SCHEMA, S3_LIST_SCHEMA, S3_PRESIGN_SCHEMA, S3_UPLOAD_SCHEMA,
    SFN_LIST_SCHEMA, SM_GET_SCHEMA, SM_PUT_SCHEMA,
    SNS_CREATE_SCHEMA, SNS_PUB_SCHEMA,
    SQS_CREATE_SCHEMA, SQS_RECV_SCHEMA, SQS_SEND_SCHEMA,
    SSM_GET_SCHEMA, SSM_LIST_SCHEMA, SSM_PUT_SCHEMA,
    make_apigw_list, make_cfn_list, make_cw_list_metrics, make_cw_put_metric,
    make_dynamo_get, make_dynamo_put, make_dynamo_query,
    make_events_list_buses, make_events_list_rules, make_events_put,
    make_iam_create_user, make_iam_list_roles, make_iam_list_users,
    make_kinesis_create, make_kinesis_list, make_kinesis_put,
    make_lambda_invoke, make_r53_list, make_s3_delete, make_s3_download,
    make_s3_list, make_s3_list_buckets, make_s3_presign, make_s3_upload,
    make_sfn_list, make_sm_get, make_sm_put,
    make_sns_create, make_sns_publish, make_sqs_create, make_sqs_receive,
    make_sqs_send,
    make_ssm_get, make_ssm_list, make_ssm_put,
)
from pysandbox.plugin.base import AgentTool, PluginDefinition
from pysandbox.plugin.registry import register_plugin


@register_plugin("localstack")
class LocalStackPlugin(PluginDefinition):

    def get_docker_config(self, plugin_name, sandbox_id, dns_zone, credentials, config, version):
        # All services available in LocalStack Community (free, no license).
        # We enable every one so users don't have to guess which are paid
        # vs. free — the container only starts what it needs on first use.
        default_services = [
            "s3", "sqs", "sns", "ses",            # messaging / storage
            "lambda",                              # compute
            "dynamodb",                            # nosql
            "kinesis", "firehose",                 # streaming
            "apigateway",                          # api management
            "cloudformation",                      # iac
            "cloudwatch", "logs",                  # observability
            "events",                              # eventbridge
            "stepfunctions",                       # orchestration
            "iam", "sts",                          # identity
            "kms", "secretsmanager",               # security
            "ssm",                                 # parameter store
            "route53",                             # dns
            "acm",                                 # certificates
            "ec2",                                 # basic compute metadata
            "resourcegroupstaggingapi",            # tagging
            "opensearch", "es",                    # search
            "redshift",                            # data warehouse (ddl)
            "swf",                                 # simple workflow
            "resource-groups",                     # grouping
            "scheduler",                           # eventbridge scheduler
            "transcribe",                          # speech to text (stub)
            "support",                             # support api (stub)
        ]
        services = ",".join(config.get("services", default_services))
        env = {
            "SERVICES": services,
            "DEFAULT_REGION": config.get("region", "us-east-1"),
            "AWS_DEFAULT_REGION": config.get("region", "us-east-1"),
            "DEBUG": "0",
        }
        # LocalStack v3+ requires a paid license (LOCALSTACK_AUTH_TOKEN).
        # If the user supplies one via config, pass it through so paid
        # features work. Otherwise the default version (1.4.0) is the
        # last free community release and doesn't need a token.
        auth_token = config.get("auth_token", "")
        if auth_token:
            env["LOCALSTACK_AUTH_TOKEN"] = auth_token
        return {
            "image": config.get("image", f"localstack/localstack:{version}"),
            "environment": env,
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
            AgentTool("s3_list", "List S3 objects in a bucket", S3_LIST_SCHEMA, make_s3_list(*args)),
            AgentTool("s3_list_buckets", "List all S3 buckets", S3_LIST_BUCKETS_SCHEMA, make_s3_list_buckets(*args)),
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
            # Kinesis
            AgentTool("kinesis_create_stream", "Create Kinesis stream", KINESIS_CREATE_SCHEMA, make_kinesis_create(*args)),
            AgentTool("kinesis_put_record", "Put record to Kinesis stream", KINESIS_PUT_SCHEMA, make_kinesis_put(*args)),
            AgentTool("kinesis_list_streams", "List Kinesis streams", KINESIS_LIST_SCHEMA, make_kinesis_list(*args)),
            # EventBridge
            AgentTool("events_put", "Put events to EventBridge", EVENTS_PUT_SCHEMA, make_events_put(*args)),
            AgentTool("events_list_rules", "List EventBridge rules", EVENTS_LIST_RULES_SCHEMA, make_events_list_rules(*args)),
            AgentTool("events_list_buses", "List event buses", EVENTS_LIST_BUSES_SCHEMA, make_events_list_buses(*args)),
            # SSM Parameter Store
            AgentTool("ssm_get_parameter", "Get SSM parameter", SSM_GET_SCHEMA, make_ssm_get(*args)),
            AgentTool("ssm_put_parameter", "Put SSM parameter", SSM_PUT_SCHEMA, make_ssm_put(*args)),
            AgentTool("ssm_list_parameters", "List SSM parameters", SSM_LIST_SCHEMA, make_ssm_list(*args)),
            # CloudWatch
            AgentTool("cloudwatch_put_metric", "Put CloudWatch metric", CW_PUT_METRIC_SCHEMA, make_cw_put_metric(*args)),
            AgentTool("cloudwatch_list_metrics", "List CloudWatch metrics", CW_LIST_METRICS_SCHEMA, make_cw_list_metrics(*args)),
            # IAM
            AgentTool("iam_create_user", "Create IAM user", IAM_CREATE_USER_SCHEMA, make_iam_create_user(*args)),
            AgentTool("iam_list_users", "List IAM users", IAM_LIST_USERS_SCHEMA, make_iam_list_users(*args)),
            AgentTool("iam_list_roles", "List IAM roles", IAM_LIST_ROLES_SCHEMA, make_iam_list_roles(*args)),
            # StepFunctions
            AgentTool("stepfunctions_list", "List state machines", SFN_LIST_SCHEMA, make_sfn_list(*args)),
            # API Gateway
            AgentTool("apigateway_list", "List REST APIs", APIGW_LIST_SCHEMA, make_apigw_list(*args)),
            # CloudFormation
            AgentTool("cloudformation_list", "List CloudFormation stacks", CFN_LIST_SCHEMA, make_cfn_list(*args)),
            # Route53
            AgentTool("route53_list_zones", "List Route53 hosted zones", R53_LIST_SCHEMA, make_r53_list(*args)),
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
