"""Cloud provisioner — AWS (boto3) with stubs for GCP/Azure."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from rich.console import Console

from cloudforge.schema import CloudProvider, LabSpec

console = Console()

# AMI for Amazon Linux 2 in us-east-1.
# Other regions need their own AMI IDs; this is used as the default.
_DEFAULT_AMI = "ami-0c02fb55956c7d316"


@dataclass
class ProvisionResult:
    success: bool
    provider: str
    lab_name: str
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseProvisioner:
    """Interface every provider must implement."""

    def __init__(self, spec: LabSpec) -> None:
        self.spec = spec
        self.resources: dict[str, str] = {}

    def provision(self) -> dict:
        raise NotImplementedError

    def get_status(self) -> str:
        raise NotImplementedError

    def tag_resources(self, resources: dict) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# AWS
# ---------------------------------------------------------------------------

class AWSProvisioner(BaseProvisioner):
    """Provisions an EC2 instance + S3 bucket directly via boto3."""

    def __init__(self, spec: LabSpec) -> None:
        super().__init__(spec)
        self._ec2 = boto3.client("ec2", region_name=spec.region)
        self._s3 = boto3.client("s3", region_name=spec.region)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provision(self) -> dict:
        """
        Create one EC2 t2.micro instance and one S3 bucket.

        Waits until the instance reaches the *running* state, then tags
        both resources.  Stores all IDs in ``self.resources`` so teardown
        can find them.

        Returns:
            {"instance_id": str, "public_ip": str, "s3_bucket": str}

        Raises:
            botocore.exceptions.ClientError on any AWS API failure.
        """
        start = time.monotonic()
        console.print(f"\n[bold cyan]  Provisioning AWS lab:[/] {self.spec.name}")

        self._launch_ec2()
        self._wait_for_running()
        self._fetch_public_ip()
        self._create_s3_bucket()
        self.tag_resources(self.resources)

        elapsed = time.monotonic() - start
        console.print(f"[bold green]  AWS lab provisioned in {elapsed:.1f}s[/]")
        return dict(self.resources)

    def get_status(self) -> str:
        """
        Return the EC2 instance state name (e.g. 'running', 'stopped').

        Returns 'not_provisioned' if no instance has been launched yet,
        or 'error: <code>' if the describe call fails.
        """
        instance_id = self.resources.get("instance_id")
        if not instance_id:
            return "not_provisioned"
        try:
            resp = self._ec2.describe_instances(InstanceIds=[instance_id])
            reservations = resp.get("Reservations", [])
            if not reservations:
                return "terminated"
            return reservations[0]["Instances"][0]["State"]["Name"]
        except ClientError as exc:
            return f"error: {exc.response['Error']['Code']}"

    def tag_resources(self, resources: dict) -> None:
        """
        Apply spec tags + standard CloudForge tags to every provisioned resource.

        Non-fatal: logs a warning on failure rather than raising so that a
        tagging hiccup never blocks provisioning or teardown.
        """
        standard = {"ManagedBy": "cloudforge", "Lab": self.spec.name}
        merged = {**self.spec.tags, **standard}
        ec2_tags = [{"Key": k, "Value": v} for k, v in merged.items()]

        if "instance_id" in resources:
            try:
                self._ec2.create_tags(
                    Resources=[resources["instance_id"]],
                    Tags=ec2_tags,
                )
                console.print("  [green]✓[/] Tagged EC2 instance.")
            except ClientError as exc:
                console.print(
                    f"  [yellow]⚠ Tagging instance failed:[/] "
                    f"{exc.response['Error']['Code']}"
                )

        if "s3_bucket" in resources:
            try:
                self._s3.put_bucket_tagging(
                    Bucket=resources["s3_bucket"],
                    Tagging={"TagSet": ec2_tags},
                )
                console.print("  [green]✓[/] Tagged S3 bucket.")
            except ClientError as exc:
                console.print(
                    f"  [yellow]⚠ Tagging bucket failed:[/] "
                    f"{exc.response['Error']['Code']}"
                )

    # ------------------------------------------------------------------
    # Private helpers (each step of provision)
    # ------------------------------------------------------------------

    def _launch_ec2(self) -> None:
        console.print(
            f"  [cyan]→[/] Launching EC2 instance "
            f"[dim]({self.spec.instance_type}, {self.spec.region})[/]…"
        )
        try:
            resp = self._ec2.run_instances(
                ImageId=_DEFAULT_AMI,
                InstanceType=self.spec.instance_type,
                MinCount=1,
                MaxCount=1,
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": f"cloudforge-{self.spec.name}"},
                            {"Key": "Lab", "Value": self.spec.name},
                            {"Key": "ManagedBy", "Value": "cloudforge"},
                        ],
                    }
                ],
            )
            instance_id = resp["Instances"][0]["InstanceId"]
            self.resources["instance_id"] = instance_id
            console.print(f"  [green]✓[/] Instance launched: [bold]{instance_id}[/]")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            msg = exc.response["Error"]["Message"]
            console.print(f"  [red]✗ EC2 launch failed:[/] {code} — {msg}")
            raise

    def _wait_for_running(self) -> None:
        instance_id = self.resources["instance_id"]
        console.print("  [cyan]→[/] Waiting for instance to reach [bold]running[/] state…")
        try:
            waiter = self._ec2.get_waiter("instance_running")
            waiter.wait(
                InstanceIds=[instance_id],
                WaiterConfig={"Delay": 5, "MaxAttempts": 40},
            )
            console.print("  [green]✓[/] Instance is running.")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            msg = exc.response["Error"]["Message"]
            console.print(f"  [red]✗ Waiter error:[/] {code} — {msg}")
            raise

    def _fetch_public_ip(self) -> None:
        instance_id = self.resources["instance_id"]
        resp = self._ec2.describe_instances(InstanceIds=[instance_id])
        public_ip: str = (
            resp["Reservations"][0]["Instances"][0].get("PublicIpAddress") or ""
        )
        self.resources["public_ip"] = public_ip
        console.print(f"  [green]✓[/] Public IP: [bold]{public_ip or '(none assigned)'}[/]")

    def _create_s3_bucket(self) -> None:
        bucket_name = f"cloudforge-{self.spec.name}-{uuid4().hex[:8]}"
        console.print(f"  [cyan]→[/] Creating S3 bucket [dim]{bucket_name}[/]…")
        try:
            # us-east-1 is the default region and must NOT include LocationConstraint
            if self.spec.region == "us-east-1":
                self._s3.create_bucket(Bucket=bucket_name)
            else:
                self._s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": self.spec.region},
                )
            self.resources["s3_bucket"] = bucket_name
            console.print(f"  [green]✓[/] S3 bucket created: [bold]{bucket_name}[/]")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            msg = exc.response["Error"]["Message"]
            console.print(f"  [red]✗ S3 creation failed:[/] {code} — {msg}")
            raise


# ---------------------------------------------------------------------------
# GCP stub
# ---------------------------------------------------------------------------

class GCPProvisioner(BaseProvisioner):
    """Stub — GCP provisioner (future phase)."""

    def provision(self) -> dict:
        console.print("[yellow]  GCP provisioner is not yet implemented.[/]")
        raise NotImplementedError("GCP provisioner not implemented")

    def get_status(self) -> str:
        return "not_provisioned"

    def tag_resources(self, resources: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# Azure stub
# ---------------------------------------------------------------------------

class AzureProvisioner(BaseProvisioner):
    """Stub — Azure provisioner (future phase)."""

    def provision(self) -> dict:
        console.print("[yellow]  Azure provisioner is not yet implemented.[/]")
        raise NotImplementedError("Azure provisioner not implemented")

    def get_status(self) -> str:
        return "not_provisioned"

    def tag_resources(self, resources: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# Registry + factory
# ---------------------------------------------------------------------------

_REGISTRY: dict[CloudProvider, type[BaseProvisioner]] = {
    CloudProvider.aws: AWSProvisioner,
    CloudProvider.gcp: GCPProvisioner,
    CloudProvider.azure: AzureProvisioner,
}


def get_provisioner(provider: CloudProvider, spec: LabSpec) -> BaseProvisioner:
    """Return an initialised provisioner for *provider*, bound to *spec*."""
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider}")
    return cls(spec)
