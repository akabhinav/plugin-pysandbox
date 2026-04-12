"""S3/AWS agent tool handlers — execute real commands via docker exec (aws CLI)."""

from __future__ import annotations

import json

S3_UPLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "key": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["bucket", "key", "body"],
}

S3_DOWNLOAD_SCHEMA = {
    "type": "object",
    "properties": {"bucket": {"type": "string"}, "key": {"type": "string"}},
    "required": ["bucket", "key"],
}

S3_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "prefix": {"type": "string", "default": ""},
    },
    "required": ["bucket"],
}

S3_LIST_BUCKETS_SCHEMA = {
    "type": "object",
    "properties": {},
}

S3_DELETE_SCHEMA = {
    "type": "object",
    "properties": {"bucket": {"type": "string"}, "key": {"type": "string"}},
    "required": ["bucket", "key"],
}

S3_PRESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "key": {"type": "string"},
        "expires_in": {"type": "integer", "default": 3600},
    },
    "required": ["bucket", "key"],
}

SQS_SEND_SCHEMA = {
    "type": "object",
    "properties": {
        "queue_url": {"type": "string"},
        "message_body": {"type": "string"},
    },
    "required": ["queue_url", "message_body"],
}

SQS_RECV_SCHEMA = {
    "type": "object",
    "properties": {
        "queue_url": {"type": "string"},
        "max_messages": {"type": "integer", "default": 1},
    },
    "required": ["queue_url"],
}

SQS_CREATE_SCHEMA = {
    "type": "object",
    "properties": {"queue_name": {"type": "string"}},
    "required": ["queue_name"],
}

SNS_PUB_SCHEMA = {
    "type": "object",
    "properties": {
        "topic_arn": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["topic_arn", "message"],
}

SNS_CREATE_SCHEMA = {
    "type": "object",
    "properties": {"topic_name": {"type": "string"}},
    "required": ["topic_name"],
}

LAMBDA_INVOKE_SCHEMA = {
    "type": "object",
    "properties": {
        "function_name": {"type": "string"},
        "payload": {"type": "string"},
    },
    "required": ["function_name"],
}

DYNAMO_PUT_SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "item": {"type": "object"},
    },
    "required": ["table_name", "item"],
}

DYNAMO_GET_SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "key": {"type": "object"},
    },
    "required": ["table_name", "key"],
}

DYNAMO_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "key_condition": {"type": "string"},
    },
    "required": ["table_name", "key_condition"],
}

SM_GET_SCHEMA = {
    "type": "object",
    "properties": {"secret_id": {"type": "string"}},
    "required": ["secret_id"],
}

SM_PUT_SCHEMA = {
    "type": "object",
    "properties": {
        "secret_id": {"type": "string"},
        "secret_value": {"type": "string"},
    },
    "required": ["secret_id", "secret_value"],
}

EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _quote(s: str) -> str:
    return s.replace("'", "'\\''")


def _aws_env(endpoint_url: str, access_key: str, secret_key: str, region: str) -> str:
    """Build env prefix for awslocal / aws CLI."""
    return (
        f"AWS_ENDPOINT_URL={endpoint_url} "
        f"AWS_ACCESS_KEY_ID={access_key} "
        f"AWS_SECRET_ACCESS_KEY={secret_key} "
        f"AWS_DEFAULT_REGION={region} "
    )


# --- S3 ---

def make_s3_upload(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        body = _quote(params["body"])
        bucket = params["bucket"]
        key = params["key"]
        cmd = f"printf '%s' '{body}' | {env} aws s3 cp - s3://{bucket}/{key} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_s3_download(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        bucket = params["bucket"]
        key = params["key"]
        cmd = f"{env} aws s3 cp s3://{bucket}/{key} - --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_s3_list_buckets(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws s3 ls --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_s3_list(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        bucket = params["bucket"]
        prefix = params.get("prefix", "")
        cmd = f"{env} aws s3 ls s3://{bucket}/{prefix} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_s3_delete(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        bucket = params["bucket"]
        key = params["key"]
        cmd = f"{env} aws s3 rm s3://{bucket}/{key} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_s3_presign(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        bucket = params["bucket"]
        key = params["key"]
        expires = params.get("expires_in", 3600)
        cmd = f"{env} aws s3 presign s3://{bucket}/{key} --expires-in {expires} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- SQS ---

def make_sqs_send(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        queue_url = params["queue_url"]
        body = _quote(params["message_body"])
        cmd = f"{env} aws sqs send-message --queue-url {queue_url} --message-body '{body}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sqs_receive(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        queue_url = params["queue_url"]
        max_msgs = params.get("max_messages", 1)
        cmd = f"{env} aws sqs receive-message --queue-url {queue_url} --max-number-of-messages {max_msgs} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sqs_create(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        name = params["queue_name"]
        cmd = f"{env} aws sqs create-queue --queue-name {name} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- SNS ---

def make_sns_publish(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        topic_arn = params["topic_arn"]
        message = _quote(params["message"])
        cmd = f"{env} aws sns publish --topic-arn {topic_arn} --message '{message}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sns_create(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        name = params["topic_name"]
        cmd = f"{env} aws sns create-topic --name {name} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- Lambda ---

def make_lambda_invoke(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        name = params["function_name"]
        payload = _quote(params.get("payload", "{}"))
        cmd = f"{env} aws lambda invoke --function-name {name} --payload '{payload}' /tmp/lambda_out.json --endpoint-url {endpoint_url} && cat /tmp/lambda_out.json"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- DynamoDB ---

def make_dynamo_put(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        table = params["table_name"]
        item = _quote(json.dumps(params["item"]))
        cmd = f"{env} aws dynamodb put-item --table-name {table} --item '{item}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dynamo_get(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        table = params["table_name"]
        key = _quote(json.dumps(params["key"]))
        cmd = f"{env} aws dynamodb get-item --table-name {table} --key '{key}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_dynamo_query(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        table = params["table_name"]
        condition = _quote(params["key_condition"])
        cmd = f"{env} aws dynamodb query --table-name {table} --key-condition-expression '{condition}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# --- Secrets Manager ---

def make_sm_get(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        secret_id = params["secret_id"]
        cmd = f"{env} aws secretsmanager get-secret-value --secret-id {secret_id} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


def make_sm_put(container_id: str, docker_runtime, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    async def handler(params: dict) -> str:
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        secret_id = params["secret_id"]
        value = _quote(params["secret_value"])
        cmd = f"{env} aws secretsmanager create-secret --name {secret_id} --secret-string '{value}' --endpoint-url {endpoint_url} || {env} aws secretsmanager put-secret-value --secret-id {secret_id} --secret-string '{value}' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── Kinesis ───────────────────────────────────────────────────────────

KINESIS_CREATE_SCHEMA = {
    "type": "object",
    "properties": {"stream_name": {"type": "string"}, "shard_count": {"type": "integer", "default": 1}},
    "required": ["stream_name"],
}
KINESIS_PUT_SCHEMA = {
    "type": "object",
    "properties": {"stream_name": {"type": "string"}, "data": {"type": "string"}, "partition_key": {"type": "string", "default": "pk"}},
    "required": ["stream_name", "data"],
}
KINESIS_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_kinesis_create(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws kinesis create-stream --stream-name {params['stream_name']} --shard-count {params.get('shard_count',1)} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_kinesis_put(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        data = _quote(params["data"])
        pk = params.get("partition_key", "pk")
        cmd = f"{env} aws kinesis put-record --stream-name {params['stream_name']} --data '{data}' --partition-key {pk} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_kinesis_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws kinesis list-streams --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── EventBridge ───────────────────────────────────────────────────────

EVENTS_PUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "detail_type": {"type": "string"},
        "detail": {"type": "string"},
        "bus_name": {"type": "string", "default": "default"},
    },
    "required": ["source", "detail_type", "detail"],
}
EVENTS_LIST_RULES_SCHEMA = {"type": "object", "properties": {"bus_name": {"type": "string", "default": "default"}}}
EVENTS_LIST_BUSES_SCHEMA = {"type": "object", "properties": {}}

def make_events_put(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        detail = _quote(params["detail"])
        cmd = f"{env} aws events put-events --entries '[{{\"Source\":\"{params['source']}\",\"DetailType\":\"{params['detail_type']}\",\"Detail\":\"{detail}\",\"EventBusName\":\"{params.get('bus_name','default')}\"}}]' --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_events_list_rules(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        bus = params.get("bus_name", "default")
        cmd = f"{env} aws events list-rules --event-bus-name {bus} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_events_list_buses(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws events list-event-buses --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── SSM Parameter Store ───────────────────────────────────────────────

SSM_GET_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}
SSM_PUT_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "param_type": {"type": "string", "default": "String"}},
    "required": ["name", "value"],
}
SSM_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_ssm_get(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws ssm get-parameter --name {params['name']} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_ssm_put(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        val = _quote(params["value"])
        ptype = params.get("param_type", "String")
        cmd = f"{env} aws ssm put-parameter --name {params['name']} --value '{val}' --type {ptype} --overwrite --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_ssm_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws ssm describe-parameters --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── CloudWatch ────────────────────────────────────────────────────────

CW_PUT_METRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "namespace": {"type": "string"},
        "metric_name": {"type": "string"},
        "value": {"type": "number"},
        "unit": {"type": "string", "default": "Count"},
    },
    "required": ["namespace", "metric_name", "value"],
}
CW_LIST_METRICS_SCHEMA = {"type": "object", "properties": {"namespace": {"type": "string"}}}

def make_cw_put_metric(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        ns = params["namespace"]
        mn = params["metric_name"]
        val = params["value"]
        unit = params.get("unit", "Count")
        cmd = f"{env} aws cloudwatch put-metric-data --namespace {ns} --metric-name {mn} --value {val} --unit {unit} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_cw_list_metrics(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        ns_flag = f"--namespace {params['namespace']}" if params.get("namespace") else ""
        cmd = f"{env} aws cloudwatch list-metrics {ns_flag} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── IAM ───────────────────────────────────────────────────────────────

IAM_CREATE_USER_SCHEMA = {"type": "object", "properties": {"user_name": {"type": "string"}}, "required": ["user_name"]}
IAM_LIST_USERS_SCHEMA = {"type": "object", "properties": {}}
IAM_LIST_ROLES_SCHEMA = {"type": "object", "properties": {}}

def make_iam_create_user(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws iam create-user --user-name {params['user_name']} --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_iam_list_users(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws iam list-users --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler

def make_iam_list_roles(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws iam list-roles --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── StepFunctions ─────────────────────────────────────────────────────

SFN_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_sfn_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws stepfunctions list-state-machines --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── API Gateway ───────────────────────────────────────────────────────

APIGW_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_apigw_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws apigateway get-rest-apis --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── CloudFormation ────────────────────────────────────────────────────

CFN_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_cfn_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws cloudformation list-stacks --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler


# ── Route53 ───────────────────────────────────────────────────────────

R53_LIST_SCHEMA = {"type": "object", "properties": {}}

def make_r53_list(container_id, docker_runtime, endpoint_url, access_key, secret_key, region="us-east-1"):
    async def handler(params):
        env = _aws_env(endpoint_url, access_key, secret_key, region)
        cmd = f"{env} aws route53 list-hosted-zones --endpoint-url {endpoint_url}"
        return await docker_runtime.exec_in_container(container_id, cmd)
    return handler
