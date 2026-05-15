#!/usr/bin/env python3
"""
Neuron AWS connectivity verifier.

Uses profile `neuron-dev` and region `us-east-1`. Run after `aws sso login --profile neuron-dev`
(or equivalent) so credentials resolve.

Dependencies: boto3
  uv run python verify_aws.py
  # or: pip install boto3 && python verify_aws.py
"""

from __future__ import annotations

import sys
import uuid
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Configuration (matches Neuron platform defaults)
# ---------------------------------------------------------------------------
AWS_PROFILE = "neuron-dev"
AWS_REGION = "us-east-1"
DYNAMODB_TABLE = "neuron-sessions"
# S3 bucket pattern: neuron-platform-docs-<12-digit account id>
S3_BUCKET_PREFIX = "neuron-platform-docs-"
# Bedrock: modelId / modelName strings evolve; these substrings match typical Sonnet 4 SKUs.
CLAUDE_SONNET_4_SUBSTRINGS = (
    "claude-sonnet-4",
    "claude-4-sonnet",
    "claude_sonnet_4",
    "sonnet-4-20",
)


def _session() -> boto3.Session:
    """Build a boto3 Session with the Neuron dev profile and region."""
    return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)


def check_credentials(session: boto3.Session) -> tuple[bool, str, str]:
    """
    Verify AWS credentials by calling STS GetCallerIdentity.

    Returns (ok, detail, account_id) — account_id is empty string if not available.
    """
    try:
        sts = session.client("sts")
        ident: dict[str, Any] = sts.get_caller_identity()
        aid = str(ident.get("Account", "") or "")
        arn = ident.get("Arn", "?")
        return True, f"account={aid} arn={arn}", aid
    except (ClientError, BotoCoreError) as e:
        return False, str(e), ""


def check_bedrock_claude_sonnet_4(session: boto3.Session) -> tuple[bool, str]:
    """
    Verify Bedrock is reachable and list_foundation_models includes Claude Sonnet 4.

    Matches modelName (e.g. \"Claude Sonnet 4\") and/or modelId substrings in CLAUDE_SONNET_4_SUBSTRINGS.
    """
    try:
        bedrock = session.client("bedrock", region_name=AWS_REGION)
        resp = bedrock.list_foundation_models()
        summaries = resp.get("modelSummaries") or []

        def summary_is_sonnet_4(m: dict[str, Any]) -> bool:
            mid = (m.get("modelId") or "").lower()
            mname = (m.get("modelName") or "").lower()
            # Console / API often label the family explicitly in modelName.
            if "sonnet 4" in mname or "claude sonnet 4" in mname:
                return True
            return any(s in mid for s in CLAUDE_SONNET_4_SUBSTRINGS)

        found_models = [m for m in summaries if summary_is_sonnet_4(m)]
        if found_models:
            preview = [m.get("modelId", "?") for m in found_models[:5]]
            return True, f"found {len(found_models)} matching model(s), modelIds={preview!r}"

        ids = [m.get("modelId", "") for m in summaries]
        # Helpful failure: show anthropic models so operator can adjust matchers
        anthropic = [mid for mid in ids if "anthropic" in mid.lower() and "claude" in mid.lower()]
        preview = anthropic[:15]
        return (
            False,
            "no Claude Sonnet 4 modelId matched "
            f"{CLAUDE_SONNET_4_SUBSTRINGS!r}; sample Claude IDs: {preview!r}",
        )
    except (ClientError, BotoCoreError) as e:
        return False, str(e)


def _ddb_key_schema(table_desc: dict[str, Any]) -> list[dict[str, str]]:
    """Extract KEY_TYPE -> AttributeName from DescribeTable response."""
    out: list[dict[str, str]] = []
    for el in table_desc.get("Table", {}).get("KeySchema", []) or []:
        out.append(
            {
                "AttributeName": el["AttributeName"],
                "KeyType": el["KeyType"],
            }
        )
    return out


def check_dynamodb_roundtrip(session: boto3.Session) -> tuple[bool, str]:
    """
    Verify DynamoDB: put a test item to neuron-sessions, get it, delete it.

    Key attributes are taken from the table's key schema (supports HASH-only or HASH+RANGE).
    """
    ddb = session.resource("dynamodb", region_name=AWS_REGION)
    client = session.client("dynamodb", region_name=AWS_REGION)

    try:
        desc = client.describe_table(TableName=DYNAMODB_TABLE)
        schema = _ddb_key_schema(desc)
        if not schema:
            return False, "table has empty KeySchema"

        # Build item: partition (and sort) keys must be present; use string values for test
        item: dict[str, Any] = {}
        key_for_get_delete: dict[str, Any] = {}
        suffix = uuid.uuid4().hex[:12]
        for el in schema:
            name = el["AttributeName"]
            kt = el["KeyType"]
            if kt == "HASH":
                val = f"__neuron_verify_pk_{suffix}"
            elif kt == "RANGE":
                val = f"__neuron_verify_sk_{suffix}"
            else:
                return False, f"unexpected KeyType {kt!r}"
            item[name] = val
            key_for_get_delete[name] = val

        item["__neuron_verify"] = True
        item["ttl"] = None  # harmless attribute if unused by app

        table = ddb.Table(DYNAMODB_TABLE)
        table.put_item(Item=item)

        got = table.get_item(Key=key_for_get_delete, ConsistentRead=True)
        body = got.get("Item")
        if not body:
            table.delete_item(Key=key_for_get_delete)
            return False, "get_item returned no Item after put_item"

        if body.get("__neuron_verify") is not True:
            table.delete_item(Key=key_for_get_delete)
            return False, f"unexpected item payload keys={list(body.keys())}"

        table.delete_item(Key=key_for_get_delete)
        return True, "put → get → delete OK"
    except (ClientError, BotoCoreError) as e:
        return False, str(e)


def check_s3_roundtrip(session: boto3.Session, account_id: str) -> tuple[bool, str]:
    """
    Verify S3: put, get, delete a small object in neuron-platform-docs-{account_id}.
    """
    bucket = f"{S3_BUCKET_PREFIX}{account_id}"
    key = f"_neuron_verify/{uuid.uuid4().hex}.txt"
    payload = b"neuron aws verify\n"
    s3 = session.client("s3", region_name=AWS_REGION)

    try:
        s3.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain")
        out = s3.get_object(Bucket=bucket, Key=key)
        body = out["Body"].read()
        if body != payload:
            s3.delete_object(Bucket=bucket, Key=key)
            return False, f"body mismatch: expected {payload!r} got {body!r}"
        s3.delete_object(Bucket=bucket, Key=key)
        return True, f"s3://{bucket}/{key} put → get → delete OK"
    except (ClientError, BotoCoreError) as e:
        return False, str(e)


def main() -> int:
    """Run all checks; print status lines and return 0 iff all pass."""
    session = _session()
    failed = False

    # 1) Credentials
    ok, detail, account_id = check_credentials(session)
    if ok:
        print(f"✅ AWS credentials: {detail}")
    else:
        failed = True
        print(f"❌ AWS credentials: {detail}")

    # 2) Bedrock + Claude Sonnet 4
    ok2, d2 = check_bedrock_claude_sonnet_4(session)
    if ok2:
        print(f"✅ Bedrock (Claude Sonnet 4): {d2}")
    else:
        failed = True
        print(f"❌ Bedrock (Claude Sonnet 4): {d2}")

    # 3) DynamoDB
    ok3, d3 = check_dynamodb_roundtrip(session)
    if ok3:
        print(f"✅ DynamoDB ({DYNAMODB_TABLE}): {d3}")
    else:
        failed = True
        print(f"❌ DynamoDB ({DYNAMODB_TABLE}): {d3}")

    # 4) S3 (depends on account id from step 1)
    if not account_id:
        failed = True
        print("❌ S3: skipped (no account id from STS)")
    else:
        ok4, d4 = check_s3_roundtrip(session, account_id)
        if ok4:
            print(f"✅ S3: {d4}")
        else:
            failed = True
            print(f"❌ S3: {d4}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
