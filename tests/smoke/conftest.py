"""
conftest.py — session-scoped fixtures for CloudForge smoke tests.

All test fixtures are derived from a single JSON state file written by the
provisioner after a successful `cloudforge provision`.  If the file is absent,
every test in the session is skipped rather than failing with an import error.

State file location: .cloudforge_state.json (project root, next to pyproject.toml)

Expected schema:
{
    "instance_id":  "i-0abc123...",
    "public_ip":    "54.x.x.x",
    "s3_bucket":    "cloudforge-my-lab-a1b2c3d4",
    "launch_time":  47.3,          # seconds from run_instances to running state
    "region":       "us-east-1"
}
"""

from __future__ import annotations

import json
import pathlib

import pytest

# ── Location of the provisioner-written state file ────────────────────────────
_STATE_FILE = pathlib.Path(".cloudforge_state.json")

_SKIP_REASON = (
    f"State file '{_STATE_FILE}' not found. "
    "Run `cloudforge provision examples/lab.yaml` to create it."
)


# ── Base fixture ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def resources() -> dict:
    """
    Read provisioned resource IDs from .cloudforge_state.json.

    Scope: session — the file is read once per pytest invocation.
    Skips the entire session if the file is missing so test output
    shows 'skipped' rather than a confusing import / attribute error.
    """
    if not _STATE_FILE.exists():
        pytest.skip(_SKIP_REASON)

    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.skip(f"State file is not valid JSON: {exc}")

    return data  # type: ignore[return-value]  # skip raises, never returns None


# ── Derived fixtures (one per resource key) ───────────────────────────────────
# Keeping these separate lets individual tests request only what they need and
# produces clearer 'skipped' messages when a specific key is absent.

@pytest.fixture(scope="session")
def instance_ip(resources: dict) -> str:
    """Public IPv4 address of the provisioned EC2 instance."""
    ip = resources.get("public_ip", "")
    if not ip:
        pytest.skip("'public_ip' not found in state file")
    return ip


@pytest.fixture(scope="session")
def instance_id(resources: dict) -> str:
    """EC2 instance ID (e.g. 'i-0abc123def456')."""
    iid = resources.get("instance_id", "")
    if not iid:
        pytest.skip("'instance_id' not found in state file")
    return iid


@pytest.fixture(scope="session")
def bucket_name(resources: dict) -> str:
    """Name of the S3 artefact bucket created by the provisioner."""
    name = resources.get("s3_bucket", "")
    if not name:
        pytest.skip("'s3_bucket' not found in state file")
    return name


@pytest.fixture(scope="session")
def aws_region(resources: dict) -> str:
    """AWS region the lab was provisioned into (defaults to us-east-1)."""
    return resources.get("region", "us-east-1")
