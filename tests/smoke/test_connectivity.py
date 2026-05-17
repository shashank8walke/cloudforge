"""Smoke tests — basic network connectivity checks for a provisioned lab."""

from __future__ import annotations

import os
import socket
import urllib.request
import urllib.error

import pytest


LAB_HOST = os.getenv("CLOUDFORGE_PUBLIC_IP") or os.getenv("CLOUDFORGE_INSTANCE_IP")
LAB_SSH_PORT = int(os.getenv("CLOUDFORGE_SSH_PORT", "22"))
HTTP_ENDPOINT = os.getenv("CLOUDFORGE_HTTP_ENDPOINT")


@pytest.mark.smoke
class TestNetworkConnectivity:
    def test_environment_variables_present(self):
        """At least one lab host variable must be injected by the provisioner."""
        has_host = bool(LAB_HOST or HTTP_ENDPOINT)
        if not has_host:
            pytest.skip("No CLOUDFORGE_* host variables set — run via `cloudforge run`")

    @pytest.mark.skipif(not LAB_HOST, reason="CLOUDFORGE_PUBLIC_IP / CLOUDFORGE_INSTANCE_IP not set")
    def test_ssh_port_reachable(self):
        """Port 22 must be reachable on the provisioned instance."""
        with socket.create_connection((LAB_HOST, LAB_SSH_PORT), timeout=10) as sock:
            banner = sock.recv(256).decode(errors="replace")
        assert "SSH" in banner, f"Expected SSH banner, got: {banner!r}"

    @pytest.mark.skipif(not LAB_HOST, reason="CLOUDFORGE_PUBLIC_IP / CLOUDFORGE_INSTANCE_IP not set")
    def test_dns_resolves_for_host(self):
        """Host must resolve via DNS (for domain-based endpoints)."""
        try:
            infos = socket.getaddrinfo(LAB_HOST, None)
            assert len(infos) > 0
        except socket.gaierror:
            # Numeric IPs won't resolve via getaddrinfo as hostname lookups — that's fine
            import re
            assert re.match(r"^\d+\.\d+\.\d+\.\d+$", LAB_HOST), f"Cannot resolve host: {LAB_HOST}"

    @pytest.mark.skipif(not HTTP_ENDPOINT, reason="CLOUDFORGE_HTTP_ENDPOINT not set")
    def test_http_endpoint_responds(self):
        """HTTP endpoint must return a 2xx or 3xx response."""
        try:
            with urllib.request.urlopen(HTTP_ENDPOINT, timeout=15) as resp:
                assert resp.status < 400, f"HTTP {resp.status} from {HTTP_ENDPOINT}"
        except urllib.error.HTTPError as exc:
            pytest.fail(f"HTTP error {exc.code} from {HTTP_ENDPOINT}")
        except urllib.error.URLError as exc:
            pytest.fail(f"Connection failed to {HTTP_ENDPOINT}: {exc.reason}")

    def test_local_dns_resolution(self):
        """Sanity: local DNS must be functional (resolves a known domain)."""
        try:
            result = socket.getaddrinfo("example.com", 80)
            assert result, "DNS returned empty result for example.com"
        except socket.gaierror as exc:
            pytest.fail(f"Local DNS broken: {exc}")

    def test_outbound_http_connectivity(self):
        """Outbound HTTP to example.com must succeed from the test runner host."""
        try:
            with urllib.request.urlopen("http://example.com", timeout=10) as resp:
                assert resp.status == 200
        except Exception as exc:
            pytest.fail(f"Outbound HTTP failed: {exc}")
