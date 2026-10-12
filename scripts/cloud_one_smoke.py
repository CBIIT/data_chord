"""Exercise the deployed task role, data plane, and selected Bedrock models."""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping

import boto3
from agent_experiment.llm.bedrock_mantle_client import make_bedrock_mantle_client
from agent_experiment.llm.openai_client import ReasoningEffort

_MODEL_IDS = ("openai.gpt-5.6-luna", "openai.gpt-5.6-sol")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _verify_storage(region: str) -> None:
    bucket = _required("DATA_CHORD_S3_BUCKET")
    prefix = _required("DATA_CHORD_S3_PREFIX").strip("/")
    key = f"{prefix}/_smoke/{uuid.uuid4().hex}.txt"
    s3 = boto3.client("s3", region_name=region)
    s3.put_object(Bucket=bucket, Key=key, Body=b"data-chord-smoke")
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        if body != b"data-chord-smoke":
            raise RuntimeError("S3 smoke object did not round-trip")
    finally:
        s3.delete_object(Bucket=bucket, Key=key)


def _verify_tables(region: str) -> None:
    dynamodb = boto3.client("dynamodb", region_name=region)
    tables = (
        _required("DATA_CHORD_REFERENCE_TABLE"),
        _required("DATA_CHORD_HARMONIZATION_CACHE_TABLE"),
        _required("DATA_CHORD_CDE_RECOMMENDATION_CACHE_TABLE"),
    )
    for table in tables:
        status = dynamodb.describe_table(TableName=table)["Table"]["TableStatus"]
        if status != "ACTIVE":
            raise RuntimeError(f"DynamoDB table is not active: {table}")

    catalog = dynamodb.query(
        TableName=tables[0],
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": "CATALOG"}},
        ConsistentRead=True,
        Limit=1,
    )
    if not catalog.get("Items"):
        raise RuntimeError("reference-data catalog is empty")


def _verify_models(region: str) -> None:
    client = make_bedrock_mantle_client(region, ReasoningEffort.LOW)
    for model_id in _MODEL_IDS:
        response = client.converse(
            modelId=model_id,
            system=[{"text": "This is a deployment health check."}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Reply with the single word READY."}],
                }
            ],
            inferenceConfig={"maxTokens": 16},
        )
        output = response.get("output")
        if not isinstance(output, Mapping) or not output.get("message"):
            raise RuntimeError(f"model returned no message: {model_id}")


def main() -> None:
    region = _required("AWS_REGION")
    _verify_storage(region)
    _verify_tables(region)
    _verify_models(region)
    print("Cloud One smoke checks passed")


if __name__ == "__main__":
    main()
