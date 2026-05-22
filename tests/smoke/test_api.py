"""
Smoke tests — AWS API checks against provisioned resources.

Verifies that the EC2 instance is in the running state via describe_instances
and that the S3 bucket supports basic object operations (put → get → delete).
"""

from __future__ import annotations

import uuid

import boto3
import pytest
from botocore.exceptions import ClientError

pytestmark = pytest.mark.smoke

# Prefix for all objects written by these tests so they are easy to identify.
_OBJECT_PREFIX = "cloudforge-smoke/"


def test_aws_describe_instance(instance_id: str, aws_region: str) -> None:
    """
    EC2 instance must be in the 'running' state.

    Uses describe_instances rather than describe_instance_status so the call
    works even when the instance's status checks haven't completed yet.
    """
    ec2 = boto3.client("ec2", region_name=aws_region)

    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        pytest.fail(f"describe_instances failed: {code}")

    reservations = resp.get("Reservations", [])
    assert reservations, f"No reservation returned for instance '{instance_id}'"

    instance = reservations[0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "running", (
        f"Instance '{instance_id}' is in state '{state}' — expected 'running'.\n"
        f"  Launch time : {instance.get('LaunchTime')}\n"
        f"  AZ          : {instance.get('Placement', {}).get('AvailabilityZone')}"
    )


def test_s3_put_get(bucket_name: str) -> None:
    """
    S3 bucket must support put → get → verify → delete round-trip.

    A unique key is used on every run so parallel test sessions never
    collide, and cleanup always happens (even when an assertion fails).
    """
    s3 = boto3.client("s3")
    key = f"{_OBJECT_PREFIX}test-{uuid.uuid4().hex[:12]}.txt"
    expected_body = f"cloudforge-smoke-test:{key}"

    # ── PUT ───────────────────────────────────────────────────────────────────
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=expected_body.encode("utf-8"),
            ContentType="text/plain",
        )
    except ClientError as exc:
        pytest.fail(
            f"PUT s3://{bucket_name}/{key} failed: "
            f"{exc.response['Error']['Code']}"
        )

    # ── GET + verify ──────────────────────────────────────────────────────────
    try:
        resp = s3.get_object(Bucket=bucket_name, Key=key)
        retrieved_body = resp["Body"].read().decode("utf-8")
    except ClientError as exc:
        pytest.fail(
            f"GET s3://{bucket_name}/{key} failed: "
            f"{exc.response['Error']['Code']}"
        )
    finally:
        # ── DELETE (best-effort cleanup) ──────────────────────────────────────
        try:
            s3.delete_object(Bucket=bucket_name, Key=key)
        except ClientError:
            pass  # test result is already determined; log nothing extra

    assert retrieved_body == expected_body, (
        f"Object body mismatch.\n"
        f"  Expected : {expected_body!r}\n"
        f"  Got      : {retrieved_body!r}"
    )
