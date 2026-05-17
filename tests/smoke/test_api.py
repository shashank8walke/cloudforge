"""Smoke tests — API / metadata endpoint checks for provisioned lab resources."""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

import pytest


API_ENDPOINT = os.getenv("CLOUDFORGE_API_ENDPOINT")
LAB_NAME = os.getenv("CLOUDFORGE_LAB_NAME", "unknown-lab")
AWS_REGION = os.getenv("CLOUDFORGE_REGION", "us-east-1")

# EC2 instance metadata v2 — only valid if tests run ON the instance
_IMDS_TOKEN_URL = "http://169.254.169.254/latest/api/token"
_IMDS_META_URL = "http://169.254.169.254/latest/meta-data/"


def _fetch_json(url: str, timeout: int = 10, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _is_on_ec2() -> bool:
    try:
        req = urllib.request.Request(_IMDS_TOKEN_URL, method="PUT", headers={"X-aws-ec2-metadata-token-ttl-seconds": "10"})
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


@pytest.mark.smoke
class TestAPIEndpoints:
    @pytest.mark.skipif(not API_ENDPOINT, reason="CLOUDFORGE_API_ENDPOINT not set")
    def test_api_health_check(self):
        """/health (or /healthz) must return HTTP 200."""
        health_url = API_ENDPOINT.rstrip("/") + "/health"
        try:
            with urllib.request.urlopen(health_url, timeout=10) as resp:
                assert resp.status == 200, f"Health check returned HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            # Some services use /healthz
            if exc.code == 404:
                healthz_url = API_ENDPOINT.rstrip("/") + "/healthz"
                with urllib.request.urlopen(healthz_url, timeout=10) as resp:
                    assert resp.status == 200
            else:
                pytest.fail(f"Health check HTTP {exc.code}")

    @pytest.mark.skipif(not API_ENDPOINT, reason="CLOUDFORGE_API_ENDPOINT not set")
    def test_api_returns_json(self):
        """Root API endpoint must return valid JSON."""
        try:
            data = _fetch_json(API_ENDPOINT, headers={"Accept": "application/json"})
            assert isinstance(data, (dict, list)), f"Expected JSON object/array, got {type(data)}"
        except (json.JSONDecodeError, urllib.error.URLError) as exc:
            pytest.fail(f"API did not return JSON: {exc}")

    @pytest.mark.skipif(not API_ENDPOINT, reason="CLOUDFORGE_API_ENDPOINT not set")
    def test_api_response_time(self):
        """API must respond within 5 seconds."""
        import time
        start = time.monotonic()
        try:
            with urllib.request.urlopen(API_ENDPOINT, timeout=5):
                pass
        except urllib.error.URLError as exc:
            pytest.fail(f"API unreachable: {exc}")
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"API too slow: {elapsed:.2f}s"


@pytest.mark.smoke
class TestAWSMetadata:
    @pytest.mark.skipif(not _is_on_ec2(), reason="Not running on an EC2 instance")
    def test_imds_token_fetch(self):
        """EC2 IMDSv2 token must be obtainable."""
        req = urllib.request.Request(
            _IMDS_TOKEN_URL,
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "10"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            token = resp.read().decode()
        assert len(token) > 0, "IMDS returned empty token"

    @pytest.mark.skipif(not _is_on_ec2(), reason="Not running on an EC2 instance")
    def test_imds_instance_id_present(self):
        """EC2 instance-id metadata must be reachable via IMDSv2."""
        token_req = urllib.request.Request(
            _IMDS_TOKEN_URL,
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "10"},
        )
        with urllib.request.urlopen(token_req, timeout=5) as resp:
            token = resp.read().decode()

        id_req = urllib.request.Request(
            _IMDS_META_URL + "instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(id_req, timeout=5) as resp:
            instance_id = resp.read().decode()
        assert instance_id.startswith("i-"), f"Unexpected instance id: {instance_id}"

    def test_lab_name_env_var(self):
        """CLOUDFORGE_LAB_NAME must be injected by the runner."""
        assert LAB_NAME != "unknown-lab", "CLOUDFORGE_LAB_NAME was not injected — run via `cloudforge run`"

    def test_aws_region_env_var(self):
        """CLOUDFORGE_REGION must be set and non-empty."""
        assert AWS_REGION, "CLOUDFORGE_REGION is not set"
        assert len(AWS_REGION) >= 9, f"Region looks malformed: {AWS_REGION}"
