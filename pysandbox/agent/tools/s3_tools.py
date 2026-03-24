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
