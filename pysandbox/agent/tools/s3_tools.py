"""S3/AWS agent tool handlers for LocalStack and MinIO plugins."""

from __future__ import annotations

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


def _make_handler(name: str, cfg: dict):
    async def handler(params: dict) -> str:
        return f"[{name}] endpoint={cfg.get('endpoint_url', '')} params={params}"
    return handler


def make_s3_upload(cfg: dict): return _make_handler("s3_upload", cfg)
def make_s3_download(cfg: dict): return _make_handler("s3_download", cfg)
def make_s3_list(cfg: dict): return _make_handler("s3_list", cfg)
def make_s3_delete(cfg: dict): return _make_handler("s3_delete", cfg)
def make_s3_presign(cfg: dict): return _make_handler("s3_presign", cfg)
def make_sqs_send(cfg: dict): return _make_handler("sqs_send", cfg)
def make_sqs_receive(cfg: dict): return _make_handler("sqs_receive", cfg)
def make_sqs_create(cfg: dict): return _make_handler("sqs_create_queue", cfg)
def make_sns_publish(cfg: dict): return _make_handler("sns_publish", cfg)
def make_sns_create(cfg: dict): return _make_handler("sns_create_topic", cfg)
def make_lambda_invoke(cfg: dict): return _make_handler("lambda_invoke", cfg)
def make_dynamo_put(cfg: dict): return _make_handler("dynamodb_put", cfg)
def make_dynamo_get(cfg: dict): return _make_handler("dynamodb_get", cfg)
def make_dynamo_query(cfg: dict): return _make_handler("dynamodb_query", cfg)
def make_sm_get(cfg: dict): return _make_handler("secretsmanager_get", cfg)
def make_sm_put(cfg: dict): return _make_handler("secretsmanager_put", cfg)
