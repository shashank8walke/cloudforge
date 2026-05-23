"""Resource cleanup — boto3-based teardown for AWS; stub fallback for GCP/Azure."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from rich.console import Console

from cloudforge.schema import CloudProvider, LabSpec

console = Console()

_STATE_FILE = Path(".cloudforge_state.json")


@dataclass
class TeardownResult:
    success: bool
    lab_name: str
    provider: str
    elapsed_seconds: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

def _read_state() -> dict | None:
    """Load .cloudforge_state.json; return None if missing or malformed."""
    if not _STATE_FILE.exists():
        return None
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# AWS boto3 teardown helpers
# ---------------------------------------------------------------------------

def _aws_terminate_instance(ec2, instance_id: str) -> None:
    """Terminate an EC2 instance and wait until it reaches the terminated state."""
    console.print(f"  [cyan]→[/] Terminating EC2 instance [bold]{instance_id}[/]…")
    ec2.terminate_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter("instance_terminated")
    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={"Delay": 5, "MaxAttempts": 60},
    )
    console.print("  [green]✓[/] Instance terminated.")


def _aws_delete_bucket(s3, bucket_name: str) -> None:
    """Empty an S3 bucket (all object versions) then delete it."""
    console.print(f"  [cyan]→[/] Deleting S3 bucket [bold]{bucket_name}[/]…")

    # Drain all objects (handles pagination automatically)
    paginator = s3.get_paginator("list_objects_v2")
    delete_count = 0
    for page in paginator.paginate(Bucket=bucket_name):
        objects = page.get("Contents", [])
        if objects:
            s3.delete_objects(
                Bucket=bucket_name,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
            delete_count += len(objects)

    if delete_count:
        console.print(f"  [green]✓[/] Deleted {delete_count} object(s) from bucket.")

    s3.delete_bucket(Bucket=bucket_name)
    console.print("  [green]✓[/] Bucket deleted.")


def _run_aws_teardown(spec: LabSpec, state: dict) -> tuple[bool, str | None]:
    """
    Terminate EC2 + delete S3 using IDs from the state dict.

    Returns (success, error_message_or_None).
    """
    region = state.get("region", spec.region)
    ec2 = boto3.client("ec2", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    errors: list[str] = []

    # ── EC2 ────────────────────────────────────────────────────────────────
    instance_id = state.get("instance_id")
    if instance_id:
        try:
            _aws_terminate_instance(ec2, instance_id)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "InvalidInstanceID.NotFound":
                console.print(
                    f"  [yellow]⚠ Instance {instance_id} not found — already terminated?[/]"
                )
            else:
                msg = (
                    f"EC2 terminate failed: {code} — "
                    f"{exc.response['Error']['Message']}"
                )
                console.print(f"  [red]✗ {msg}[/]")
                errors.append(msg)
    else:
        console.print("  [yellow]⚠ No instance_id in state — skipping EC2 teardown.[/]")

    # ── S3 ─────────────────────────────────────────────────────────────────
    bucket_name = state.get("s3_bucket")
    if bucket_name:
        try:
            _aws_delete_bucket(s3, bucket_name)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            http = exc.response["ResponseMetadata"]["HTTPStatusCode"]
            if http == 404 or code == "NoSuchBucket":
                console.print(
                    f"  [yellow]⚠ Bucket {bucket_name} not found — already deleted?[/]"
                )
            else:
                msg = (
                    f"S3 delete failed: {code} — "
                    f"{exc.response['Error']['Message']}"
                )
                console.print(f"  [red]✗ {msg}[/]")
                errors.append(msg)
    else:
        console.print("  [yellow]⚠ No s3_bucket in state — skipping S3 teardown.[/]")

    return len(errors) == 0, "; ".join(errors) if errors else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_teardown(spec: LabSpec) -> TeardownResult:
    """
    Destroy all provisioned resources for *spec*.

    For AWS: reads .cloudforge_state.json, terminates the EC2 instance via
    boto3, empties and deletes the S3 bucket, then removes the state file.

    For GCP/Azure: returns a non-fatal "not implemented" result (stubs).
    """
    start = time.monotonic()
    console.print(f"\n[bold yellow]  Teardown:[/] {spec.name} ({spec.provider.value})")

    if spec.provider == CloudProvider.aws:
        state = _read_state()
        if state is None:
            return TeardownResult(
                success=False,
                lab_name=spec.name,
                provider=spec.provider.value,
                elapsed_seconds=time.monotonic() - start,
                error=(
                    f"State file '{_STATE_FILE}' not found or unreadable. "
                    "Run 'cloudforge provision' first, or delete resources manually."
                ),
            )

        ok, error = _run_aws_teardown(spec, state)
        elapsed = time.monotonic() - start

        if ok:
            # Remove the state file only on a clean teardown
            if _STATE_FILE.exists():
                _STATE_FILE.unlink()
                console.print(f"  [dim]State file {_STATE_FILE} removed.[/]")
            console.print(f"[bold green]  AWS teardown complete in {elapsed:.1f}s[/]")
        else:
            console.print("[bold red]  AWS teardown had errors — state file retained.[/]")

        return TeardownResult(
            success=ok,
            lab_name=spec.name,
            provider=spec.provider.value,
            elapsed_seconds=elapsed,
            error=error,
        )

    # ── GCP / Azure — stubs ────────────────────────────────────────────────
    console.print(
        f"  [yellow]⚠ boto3 teardown not implemented for {spec.provider.value}.[/]"
    )
    return TeardownResult(
        success=False,
        lab_name=spec.name,
        provider=spec.provider.value,
        elapsed_seconds=time.monotonic() - start,
        error=f"Teardown not implemented for provider: {spec.provider.value}",
    )
