"""Cloud provisioner — AWS (boto3) with stubs for GCP/Azure."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
from rich.console import Console

from cloudforge.schema import CloudProvider, LabSpec

console = Console()

TERRAFORM_AWS_DIR = Path(__file__).parent.parent / "terraform" / "aws"
TERRAFORM_GCP_DIR = Path(__file__).parent.parent / "terraform" / "gcp"


@dataclass
class ProvisionResult:
    success: bool
    provider: str
    lab_name: str
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_seconds: float = 0.0


class BaseProvisioner:
    def provision(self, spec: LabSpec) -> ProvisionResult:
        raise NotImplementedError

    def get_outputs(self, spec: LabSpec) -> dict[str, Any]:
        raise NotImplementedError


class AWSProvisioner(BaseProvisioner):
    """Provisions AWS resources via Terraform + boto3 health checks."""

    def __init__(self) -> None:
        self._ec2 = None
        self._s3 = None

    def _ec2_client(self, region: str):
        if self._ec2 is None:
            self._ec2 = boto3.client("ec2", region_name=region)
        return self._ec2

    def _s3_client(self):
        if self._s3 is None:
            self._s3 = boto3.client("s3")
        return self._s3

    def _run_terraform(self, tf_dir: Path, action: str, var_file: Path | None = None) -> tuple[bool, str]:
        cmd = ["terraform", action, "-auto-approve", "-no-color"]
        if var_file:
            cmd += [f"-var-file={var_file}"]
        try:
            result = subprocess.run(cmd, cwd=tf_dir, capture_output=True, text=True, timeout=600)
            return result.returncode == 0, result.stdout + result.stderr
        except FileNotFoundError:
            return False, "terraform binary not found — install Terraform >= 1.6"
        except subprocess.TimeoutExpired:
            return False, "Terraform timed out after 600 s"

    def _write_var_file(self, spec: LabSpec, tf_dir: Path) -> Path:
        var_file = tf_dir / f"{spec.name}.auto.tfvars.json"
        var_file.write_text(json.dumps(spec.to_terraform_vars(), indent=2))
        return var_file

    def provision(self, spec: LabSpec) -> ProvisionResult:
        start = time.monotonic()
        console.print(f"[bold cyan]  Provisioning AWS lab:[/] {spec.name}")

        var_file = self._write_var_file(spec, TERRAFORM_AWS_DIR)

        console.print("  Running [green]terraform init[/]…")
        ok, out = self._run_terraform(TERRAFORM_AWS_DIR, "init")
        if not ok:
            return ProvisionResult(False, "aws", spec.name, error=out, elapsed_seconds=time.monotonic() - start)

        console.print("  Running [green]terraform apply[/]…")
        ok, out = self._run_terraform(TERRAFORM_AWS_DIR, "apply", var_file)
        if not ok:
            return ProvisionResult(False, "aws", spec.name, error=out, elapsed_seconds=time.monotonic() - start)

        outputs = self.get_outputs(spec)
        elapsed = time.monotonic() - start
        console.print(f"[bold green]  AWS lab provisioned in {elapsed:.1f}s[/]")
        return ProvisionResult(True, "aws", spec.name, outputs=outputs, elapsed_seconds=elapsed)

    def get_outputs(self, spec: LabSpec) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=TERRAFORM_AWS_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                raw = json.loads(result.stdout)
                return {k: v.get("value") for k, v in raw.items()}
        except Exception:
            pass
        return {}

    def list_lab_instances(self, spec: LabSpec) -> list[dict[str, Any]]:
        ec2 = self._ec2_client(spec.instance.region)
        response = ec2.describe_instances(
            Filters=[{"Name": "tag:Lab", "Values": [spec.name]}, {"Name": "instance-state-name", "Values": ["running", "pending"]}]
        )
        instances = []
        for reservation in response.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                instances.append({"id": inst["InstanceId"], "state": inst["State"]["Name"], "public_ip": inst.get("PublicIpAddress")})
        return instances


class GCPProvisioner(BaseProvisioner):
    """Stub — GCP provisioner (Phase 2)."""

    def provision(self, spec: LabSpec) -> ProvisionResult:
        console.print("[yellow]  GCP provisioner is a stub — not yet implemented.[/]")
        return ProvisionResult(False, "gcp", spec.name, error="GCP provisioner not implemented in Phase 1")

    def get_outputs(self, spec: LabSpec) -> dict[str, Any]:
        return {}


class AzureProvisioner(BaseProvisioner):
    """Stub — Azure provisioner (Phase 2)."""

    def provision(self, spec: LabSpec) -> ProvisionResult:
        console.print("[yellow]  Azure provisioner is a stub — not yet implemented.[/]")
        return ProvisionResult(False, "azure", spec.name, error="Azure provisioner not implemented in Phase 1")

    def get_outputs(self, spec: LabSpec) -> dict[str, Any]:
        return {}


_REGISTRY: dict[CloudProvider, type[BaseProvisioner]] = {
    CloudProvider.aws: AWSProvisioner,
    CloudProvider.gcp: GCPProvisioner,
    CloudProvider.azure: AzureProvisioner,
}


def get_provisioner(provider: CloudProvider) -> BaseProvisioner:
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider}")
    return cls()
