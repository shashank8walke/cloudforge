"""
Smoke tests — network connectivity checks against a provisioned lab.

All tests receive their target addresses from the session-scoped fixtures
defined in conftest.py, which reads .cloudforge_state.json.  If the state
file is absent, the whole module is skipped by the fixture layer.
"""

from __future__ import annotations

import socket

import boto3
import pytest
from botocore.exceptions import ClientError

pytestmark = pytest.mark.smoke


# ── TCP helper ────────────────────────────────────────────────────────────────

def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> None:
    """
    Open a TCP connection to host:port within *timeout* seconds.
    Raises pytest.fail on timeout or connection refusal.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except socket.timeout:
        pytest.fail(
            f"Port {port} on {host} did not respond within {timeout}s "
            f"(firewall / SG rule may be blocking it)"
        )
    except ConnectionRefusedError:
        pytest.fail(
            f"Port {port} on {host} actively refused the connection "
            f"(no service listening on that port)"
        )
    except OSError as exc:
        pytest.fail(f"Could not reach {host}:{port} — {exc}")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_ssh_port_open(instance_ip: str) -> None:
    """Port 22 must accept a TCP connection within 3 seconds."""
    _tcp_probe(instance_ip, 22, timeout=3.0)


def test_http_port_open(instance_ip: str) -> None:
    """Port 80 must accept a TCP connection within 3 seconds."""
    _tcp_probe(instance_ip, 80, timeout=3.0)


def test_s3_bucket_exists(bucket_name: str) -> None:
    """
    S3 bucket created by the provisioner must exist and be accessible.

    boto3 head_bucket returns 200 if the bucket exists and the caller
    has s3:ListBucket permission.  A 403 means the bucket exists but
    access is denied; a 404 means it does not exist at all.
    """
    s3 = boto3.client("s3")
    try:
        s3.head_bucket(Bucket=bucket_name)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        http = exc.response["ResponseMetadata"]["HTTPStatusCode"]
        if http == 404:
            pytest.fail(f"Bucket '{bucket_name}' does not exist (404)")
        elif http == 403:
            pytest.fail(
                f"Bucket '{bucket_name}' exists but access denied (403) — "
                "check IAM permissions for s3:ListBucket"
            )
        else:
            pytest.fail(f"head_bucket failed with {code} (HTTP {http})")
