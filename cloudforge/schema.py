"""YAML spec schema — validated with Pydantic v2."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, field_validator


class CloudProvider(str, Enum):
    aws = "aws"
    gcp = "gcp"
    azure = "azure"


class LabSpec(BaseModel):
    name: str = Field(description="Unique lab identifier")
    provider: CloudProvider = Field(description="Cloud provider: aws | gcp | azure")
    region: str = Field(default="us-east-1", description="Target region")
    instance_type: Annotated[str, Field(min_length=1, description="Instance / machine type")]
    storage_gb: Annotated[int, Field(ge=1, le=100, description="Root volume size in GB")] = 20
    tags: dict[str, str] = Field(default_factory=dict)
    tests: Annotated[list[str], Field(min_length=1, description="Test suite names to run")]
    teardown_on_success: bool = Field(default=True, description="Destroy lab when all tests pass")
    teardown_on_failure: bool = Field(default=False, description="Destroy lab even when tests fail")

    @field_validator("instance_type")
    @classmethod
    def instance_type_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("instance_type must be a non-empty string")
        return v

    @field_validator("tests")
    @classmethod
    def tests_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("tests must contain at least one item")
        blanks = [t for t in v if not t.strip()]
        if blanks:
            raise ValueError(f"test names must be non-empty strings, got: {blanks}")
        return v


def load_spec(path: str) -> LabSpec:
    """Read a YAML lab spec from *path* and return a validated LabSpec."""
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    return LabSpec.model_validate(raw)
