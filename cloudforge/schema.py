"""YAML spec schema — validated with Pydantic v2."""

from __future__ import annotations

from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class CloudProvider(str, Enum):
    aws = "aws"
    gcp = "gcp"
    azure = "azure"


class InstanceSpec(BaseModel):
    type: str = Field(default="t3.micro", description="Instance / machine type")
    count: int = Field(default=1, ge=1, le=50)
    ami: str | None = None
    region: str = "us-east-1"
    tags: dict[str, str] = Field(default_factory=dict)


class NetworkSpec(BaseModel):
    vpc_cidr: str = "10.0.0.0/16"
    public_subnets: list[str] = Field(default_factory=lambda: ["10.0.1.0/24"])
    private_subnets: list[str] = Field(default_factory=list)
    enable_nat_gateway: bool = False


class StorageSpec(BaseModel):
    bucket_name: str | None = None
    size_gb: int = Field(default=20, ge=1, le=16384)
    type: str = "gp3"


class TestSuiteSpec(BaseModel):
    path: str = Field(description="Path to pytest test directory or file")
    markers: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=300, ge=10)
    env_vars: dict[str, str] = Field(default_factory=dict)


class LifecycleSpec(BaseModel):
    on_provision: list[str] = Field(default_factory=list, description="Shell commands to run after provisioning")
    on_teardown: list[str] = Field(default_factory=list, description="Shell commands to run before teardown")
    auto_teardown: bool = Field(default=True, description="Tear down after tests complete")
    teardown_on_failure: bool = Field(default=False, description="Tear down even if tests fail")


class LabSpec(BaseModel):
    name: str = Field(description="Unique lab identifier")
    provider: CloudProvider
    description: str = ""
    instance: InstanceSpec = Field(default_factory=InstanceSpec)
    network: NetworkSpec = Field(default_factory=NetworkSpec)
    storage: StorageSpec | None = None
    tests: list[TestSuiteSpec] = Field(default_factory=list)
    lifecycle: LifecycleSpec = Field(default_factory=LifecycleSpec)
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_aws_ami(self) -> "LabSpec":
        if self.provider == CloudProvider.aws and self.instance.ami is None:
            # Default community AMI for us-east-1 (Amazon Linux 2023)
            self.instance.ami = "ami-0c02fb55956c7d316"
        return self

    def to_terraform_vars(self) -> dict[str, Any]:
        return {
            "lab_name": self.name,
            "instance_type": self.instance.type,
            "instance_count": self.instance.count,
            "ami_id": self.instance.ami,
            "region": self.instance.region,
            "vpc_cidr": self.network.vpc_cidr,
            "public_subnets": self.network.public_subnets,
            "tags": {**self.labels, "ManagedBy": "cloudforge", "Lab": self.name},
        }


def load_lab_spec(path: str) -> LabSpec:
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    return LabSpec.model_validate(raw)
