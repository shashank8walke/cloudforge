# CloudForge — Complete Technical Reference: Phase 1 & Phase 2

> This document is a full walkthrough of the CloudForge project — what it is, why it exists,
> every tool and technology used, how the codebase is structured, and exactly what was built
> in each phase. Use this to prepare for discussions, interviews, or onboarding.

---

## Table of Contents

1. [The Problem Being Solved](#1-the-problem-being-solved)
2. [What CloudForge Does](#2-what-cloudforge-does)
3. [Technology Stack — Every Tool Explained](#3-technology-stack--every-tool-explained)
4. [Repository Structure — Every File Explained](#4-repository-structure--every-file-explained)
5. [Architecture & Data Flow](#5-architecture--data-flow)
6. [Phase 1 — Project Scaffold & Full Lifecycle](#6-phase-1--project-scaffold--full-lifecycle)
7. [Phase 2 — Schema Redesign with Pydantic v2](#7-phase-2--schema-redesign-with-pydantic-v2)
8. [Phase 1 vs Phase 2 — What Changed and Why](#8-phase-1-vs-phase-2--what-changed-and-why)
9. [Key Concepts & Terminology Dictionary](#9-key-concepts--terminology-dictionary)
10. [Design Decisions & Trade-offs](#10-design-decisions--trade-offs)

---

## 1. The Problem Being Solved

### The Manual Pain

QA engineers and DevOps teams working with cloud environments face a repetitive three-step problem every time they need to test something:

```
Step 1 — Spin up:   Log into AWS console → create VPC → create subnet → launch EC2 → wait 5 mins
Step 2 — Test:      SSH in → install deps → run tests → collect results manually
Step 3 — Tear down: Remember to delete everything (often forgotten) → surprise $300 AWS bill
```

This is done manually, takes 30–60 minutes per environment, is error-prone, and constantly leaves **orphaned resources** (running EC2 instances, VPCs, S3 buckets nobody deleted) accumulating cost.

### The CloudForge Solution

One command, one YAML file:

```bash
cloudforge run examples/lab.yaml --html-report
```

This single command:
1. Reads a YAML spec describing the desired environment
2. Validates the spec (rejects bad configs before touching the cloud)
3. Provisions the cloud resources via Terraform
4. Runs automated pytest smoke test suites against the live environment
5. Tears down everything automatically when done
6. Generates a JSON and HTML report of what happened

---

## 2. What CloudForge Does

### The Full Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  YAML Spec  │────▶│  Provision  │────▶│    Test     │────▶│  Teardown   │
│  (Input)    │     │  (AWS/GCP)  │     │  (pytest)   │     │  (destroy)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                     │
                                                              ┌─────────────┐
                                                              │   Report    │
                                                              │ (JSON/HTML) │
                                                              └─────────────┘
```

### CLI Commands Available

| Command | What it does |
|---|---|
| `cloudforge run lab.yaml` | Full lifecycle: provision → test → teardown |
| `cloudforge provision lab.yaml` | Only provision (no tests, no teardown) |
| `cloudforge test lab.yaml` | Only run tests (lab already provisioned) |
| `cloudforge destroy lab.yaml` | Only destroy resources |
| `cloudforge validate lab.yaml` | Only validate the YAML spec (no cloud calls) |

---

## 3. Technology Stack — Every Tool Explained

### Python 3.11+

**What:** The programming language used for all of CloudForge's application code.

**Why 3.11+:** Python 3.11 introduced significant performance improvements (~25% faster). It also gave us `tomllib` in the standard library and better error messages. The `from __future__ import annotations` at the top of every file enables postponed evaluation of type hints — meaning you can write `str | None` instead of `Optional[str]` without import errors.

**Used in:** Every `.py` file in `cloudforge/` and `tests/`.

---

### Click 8.x

**What:** A Python library for building Command Line Interfaces (CLIs).

**Why Click over argparse:** Python's built-in `argparse` is verbose and produces ugly help text. Click uses decorators to declare commands cleanly:

```python
# With Click:
@cli.command()
@click.argument("spec_file")
@click.option("--html-report", is_flag=True)
def run(spec_file, html_report):
    ...

# The same thing with argparse would be ~15 lines of parser setup code.
```

**Key concepts used:**
- `@click.group()` — Makes `cli` a group that holds sub-commands (`run`, `provision`, `test`, etc.)
- `@click.command()` — Registers a function as a sub-command
- `@click.argument()` — Positional argument (required, no `--` prefix)
- `@click.option()` — Optional flag (`--html-report`, `--no-teardown`)
- `is_flag=True` — Makes an option a boolean toggle (`--no-teardown` sets it to `True`)
- `click.Path(exists=True)` — Click validates the file exists before your code runs
- `@click.version_option()` — Adds `--version` automatically

**Entry point:** Defined in `pyproject.toml` as `cloudforge = "cloudforge.cli:cli"`, which means when you type `cloudforge` in the terminal, Python finds `cli.py` and calls the `cli()` function.

**File:** `cloudforge/cli.py`

---

### Pydantic v2

**What:** A Python data validation library. You define a class with typed fields, and Pydantic validates that incoming data matches those types and constraints.

**Why Pydantic v2 over v1:** Pydantic v2 was rewritten in Rust (via the `pydantic-core` library), making it 5–50x faster than v1. It also changed how validators are written — from `@validator` (v1) to `@field_validator` (v2).

**Why Pydantic over plain dicts:** When you load a YAML file, you get a raw Python `dict`. If a key is missing or has the wrong type, you won't find out until deep inside your business logic — producing a confusing error far from the source. Pydantic catches all of that at the boundary (load time) with a clean, structured error message.

```python
# Without Pydantic: silent bug
spec = yaml.safe_load(file)
print(spec["storage_gb"] * 2)  # Crashes if missing or wrong type — WHERE did it fail?

# With Pydantic: fail fast at the boundary
spec = LabSpec.model_validate(yaml.safe_load(file))
# ValueError: storage_gb must be between 1 and 100  ← clear, immediate, actionable
```

**Key Pydantic v2 concepts used:**

| Concept | What it does | Where used |
|---|---|---|
| `BaseModel` | Base class for all Pydantic models | `LabSpec` |
| `Field(ge=1, le=100)` | Numeric range constraint (ge=greater-or-equal, le=less-or-equal) | `storage_gb` |
| `Field(min_length=1)` | String/list length constraint | `instance_type`, `tests` |
| `Field(default_factory=dict)` | Default value that's a mutable object (can't use `default={}`) | `tags` |
| `@field_validator("field_name")` | Custom validation function for a specific field | `instance_type`, `tests` |
| `@classmethod` | Required on field validators in v2 | All validators |
| `model_validate(raw_dict)` | Parse and validate a plain dict into the model | `load_spec()` |
| `Annotated[type, Field(...)]` | Attach Field constraints to a type using Python's type system | `instance_type`, `storage_gb`, `tests` |
| `str | None` | Union type (Python 3.10+ syntax) | Optional fields |
| `CloudProvider(str, Enum)` | Enum that IS a string — `CloudProvider.aws == "aws"` is `True` | `provider` field |

**File:** `cloudforge/schema.py`

---

### boto3

**What:** Amazon's official Python SDK for AWS. Lets you control AWS services (EC2, S3, IAM, etc.) programmatically.

**Why boto3 alongside Terraform:** Terraform handles resource creation/destruction. boto3 is used for runtime queries — things Terraform doesn't track, like "is this instance currently running?" or "describe all instances with this tag". In later phases, boto3 would also handle pre-flight checks (does the AMI exist? does the IAM role have required permissions?).

**Key usage in CloudForge:**
```python
# Create an EC2 client for a specific region
ec2 = boto3.client("ec2", region_name="us-east-1")

# Query running instances with a specific tag
response = ec2.describe_instances(
    Filters=[
        {"Name": "tag:Lab", "Values": ["my-test-lab"]},
        {"Name": "instance-state-name", "Values": ["running"]}
    ]
)
```

**Files:** `cloudforge/provisioner.py`

---

### Terraform (>= 1.6)

**What:** An Infrastructure-as-Code (IaC) tool. You write declarative `.tf` files describing what cloud resources you want, and Terraform figures out how to create, update, or destroy them to match.

**Declarative vs Imperative:**
- **Imperative** (boto3 only): "Create a VPC. Now create a subnet. Now create an EC2 instance in that subnet." You manage the order and state.
- **Declarative** (Terraform): "I want this VPC, this subnet, and this EC2 instance." Terraform computes the dependency graph and execution order for you.

**Key Terraform concepts used in `terraform/aws/main.tf`:**

| Concept | Example | Meaning |
|---|---|---|
| `terraform {}` block | `required_version = ">= 1.6"` | Pin minimum Terraform version |
| `required_providers` | `hashicorp/aws ~> 5.0` | Pin provider version (~> means 5.x but not 6.x) |
| `provider "aws"` | `region = var.region` | Configure the AWS provider |
| `variable` | `variable "instance_type"` | Input parameter — can be set from outside |
| `resource` | `resource "aws_vpc" "lab"` | A real AWS resource to create |
| `data` | `data "aws_availability_zones"` | Read-only query of existing AWS state |
| `output` | `output "public_ip"` | Values Terraform exposes after apply (parsed by CloudForge) |
| `count` | `count = var.instance_count` | Create multiple identical resources |
| `count.index` | `[count.index]` | Index of current resource in a multi-count block |
| `merge()` | `merge(var.tags, {Name = "..."})` | Merge two tag maps |
| `var.xxx` | `var.region` | Reference a declared variable |
| `resource.type.name.attr` | `aws_vpc.lab.id` | Reference an attribute of another resource |

**Why Terraform over CloudFormation:** CloudFormation is AWS-only. Terraform is multi-cloud (AWS, GCP, Azure use the same tool and CLI). Since CloudForge targets multi-cloud by design, Terraform is the natural fit.

**How CloudForge drives Terraform:**

```
1. Write a .tfvars.json file with values from the LabSpec (lab_name, region, instance_type, etc.)
2. Run: terraform init   (download providers)
3. Run: terraform apply  (create resources)
4. Run: terraform output -json  (read back IPs, VPC IDs, etc.)
5. Run: terraform destroy  (delete everything)
```

All of this happens via `subprocess.run()` inside `provisioner.py`.

**Files:** `terraform/aws/main.tf`, `terraform/gcp/main.tf`

---

### pytest 8.x

**What:** Python's de-facto testing framework. Discovers and runs test functions/classes, handles assertions, and reports results.

**Key pytest concepts used:**

| Concept | Example | Meaning |
|---|---|---|
| `def test_xxx(self)` | `def test_ssh_port_reachable` | Any function starting with `test_` is auto-discovered |
| `class TestXxx` | `class TestNetworkConnectivity` | Group related tests — class must start with `Test` |
| `pytest.mark.smoke` | `@pytest.mark.smoke` | Custom marker — can filter with `-m smoke` |
| `pytest.mark.skipif` | `@pytest.mark.skipif(not LAB_HOST, ...)` | Skip test if condition is true |
| `pytest.skip()` | `pytest.skip("reason")` | Skip a test at runtime |
| `pytest.fail()` | `pytest.fail("message")` | Explicitly fail a test with a message |
| `assert` | `assert resp.status == 200` | pytest rewrites `assert` to give detailed failure info |

**How CloudForge runs pytest:** Not by importing it, but by spawning it as a subprocess:
```python
subprocess.run(["python", "-m", "pytest", "tests/smoke/test_connectivity.py", "-v", "--tb=short"])
```
This isolates test execution and lets CloudForge capture stdout/stderr to parse pass/fail counts.

**Files:** `tests/smoke/test_connectivity.py`, `tests/smoke/test_api.py`

---

### PyYAML 6.x

**What:** Python library for reading and writing YAML files.

**Why YAML over JSON/TOML for specs:** YAML supports comments (`# this is a comment`), is less noisy than JSON (no quotes on keys, no commas), and is widely used in DevOps tooling (Kubernetes manifests, GitHub Actions, Docker Compose). It's the natural format for config that humans write by hand.

**Key usage:**
```python
import yaml

with open("lab.yaml") as fh:
    raw = yaml.safe_load(fh)  # Returns a plain Python dict
# raw = {"name": "my-test-lab", "provider": "aws", ...}
```

`safe_load` is used instead of `load` — `yaml.load()` can execute arbitrary Python via YAML tags (`!!python/object`), which is a security risk. `safe_load` only parses standard YAML types.

**File:** `cloudforge/schema.py` (`load_spec` function)

---

### Rich 13.x

**What:** A Python library for beautiful terminal output — colors, tables, progress bars, markdown, panels.

**Why Rich:** Plain `print()` output in a CLI tool looks amateurish and is hard to scan. Rich makes status messages color-coded and results appear as formatted tables.

**Key Rich concepts used:**

| Usage | Code | Output |
|---|---|---|
| Color markup | `console.print("[bold green]OK[/]")` | **OK** in green |
| Nested markup | `"[bold cyan]Provisioning:[/] {name}"` | "Provisioning:" in bold cyan, name in default |
| Table | `Table(title="...")` with `add_column` / `add_row` | Formatted grid in terminal |
| `Console()` | Module-level singleton | Thread-safe output handle |

**Files:** Every module in `cloudforge/` uses `Console()`.

---

### setuptools + pyproject.toml

**What:** `pyproject.toml` is the modern Python project configuration file (PEP 517/518). It replaces `setup.py`. `setuptools` is the build backend that reads it and packages the project.

**Key sections:**

```toml
[project.scripts]
cloudforge = "cloudforge.cli:cli"
# ↑ This creates the `cloudforge` terminal command.
# When you run `pip install -e .`, pip installs a script that calls cli() in cli.py.

[project.optional-dependencies]
dev = ["pytest-cov", "ruff", "mypy", "boto3-stubs[ec2,s3,iam]"]
# ↑ Install with: pip install -e ".[dev]"
# These are dev-only tools not needed in production.
```

**`-e` flag (editable install):** `pip install -e .` installs the package in "editable" mode — the installed `cloudforge` command points directly at your source files, so changes take effect immediately without reinstalling.

---

### ruff

**What:** An extremely fast Python linter and formatter (written in Rust). Replaces flake8, isort, and parts of pylint in a single tool.

**Configured in `pyproject.toml`:**
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
```

---

### mypy

**What:** Static type checker for Python. Reads type annotations and reports type errors without running the code.

**Why:** Python is dynamically typed — you can pass a string where an int is expected and only find out at runtime. mypy catches these at "compile time" (before running).

---

### boto3-stubs

**What:** Type stubs for boto3. boto3 itself has no type annotations (it's auto-generated). boto3-stubs provides `.pyi` stub files so mypy and IDEs can type-check boto3 calls.

```toml
"boto3-stubs[ec2,s3,iam]"
# ↑ Only install stubs for the services we use.
```

---

### GitHub CLI (gh)

**What:** Official command-line tool for GitHub operations — creating repos, PRs, issues, etc.

**How used:** `gh repo create cloudforge --public --source . --remote origin --push` created the GitHub repository and pushed the initial commit in one command.

---

## 4. Repository Structure — Every File Explained

```
cloudforge/                        ← Git repo root
│
├── cloudforge/                    ← Python package (the application)
│   ├── __init__.py                ← Marks this directory as a Python package (empty)
│   ├── cli.py                     ← CLI entrypoint — all 5 commands live here
│   ├── schema.py                  ← Pydantic model for the YAML lab spec
│   ├── provisioner.py             ← Cloud resource creation (AWS live, GCP/Azure stubs)
│   ├── runner.py                  ← Pytest execution engine
│   ├── teardown.py                ← Resource destruction via terraform destroy
│   └── reporter.py                ← JSON + HTML report builder
│
├── tests/                         ← Test directory
│   ├── __init__.py                ← Makes tests/ a Python package (needed for imports)
│   └── smoke/                     ← Smoke test suites (quick "is it alive?" checks)
│       ├── __init__.py
│       ├── test_connectivity.py   ← SSH, DNS, HTTP connectivity checks
│       └── test_api.py            ← API health, JSON response, EC2 IMDSv2 checks
│
├── terraform/                     ← Infrastructure-as-Code
│   ├── aws/
│   │   └── main.tf                ← Full AWS infrastructure: VPC, SG, EC2, outputs
│   └── gcp/
│       └── main.tf                ← GCP stub (commented out, Phase 2 placeholder)
│
├── examples/
│   └── lab.yaml                   ← Example lab spec — the input format for CloudForge
│
├── pyproject.toml                 ← Project metadata, dependencies, tool config
├── README.md                      ← Short usage guide
├── phase1-phase2.md               ← This document
└── .gitignore                     ← Files Git should not track
```

### The `__init__.py` files

An empty `__init__.py` file tells Python "this directory is a package." Without it, `from cloudforge.schema import LabSpec` would fail — Python wouldn't know to look inside the `cloudforge/` directory.

### The `.gitignore`

Critical entries:
- `**/.terraform/` — Terraform downloads provider plugins here (~50MB); never commit
- `*.tfstate` — Terraform state files contain sensitive data (IPs, resource IDs); never commit
- `*.auto.tfvars.json` — CloudForge writes these dynamically at runtime; never commit
- `.venv/` — Virtual environment; never commit (each developer creates their own)
- `reports/` — Generated HTML/JSON reports; exclude from version control

---

## 5. Architecture & Data Flow

### How a `cloudforge run lab.yaml` flows through the codebase

```
cli.py: run()
  │
  ├─ load_spec("lab.yaml")                    ← schema.py
  │    └─ yaml.safe_load() → LabSpec.model_validate()
  │         └─ Pydantic validates all fields, raises ValueError if invalid
  │
  ├─ get_provisioner(spec.provider)            ← provisioner.py
  │    └─ Returns AWSProvisioner() instance
  │
  ├─ provisioner.provision(spec)               ← provisioner.py
  │    ├─ _write_var_file() → writes my-test-lab.auto.tfvars.json
  │    ├─ subprocess: terraform init
  │    ├─ subprocess: terraform apply
  │    └─ subprocess: terraform output -json → parse → ProvisionResult(outputs={...})
  │
  ├─ run_suites(spec, provision_result.outputs) ← runner.py
  │    ├─ _build_env() → copies os.environ, adds CLOUDFORGE_* vars from outputs
  │    ├─ for each test name in spec.tests:
  │    │    ├─ _resolve_path("connectivity") → "tests/smoke/test_connectivity.py"
  │    │    ├─ subprocess: python -m pytest tests/smoke/test_connectivity.py -v
  │    │    └─ _parse_pytest_output() → SuiteResult(passed=5, failed=0, ...)
  │    └─ Returns RunResult(suites=[...])
  │
  ├─ run_teardown(spec)                        ← teardown.py (if teardown conditions met)
  │    ├─ subprocess: terraform destroy -auto-approve
  │    └─ deletes my-test-lab.auto.tfvars.json
  │
  ├─ build_report(...)                         ← reporter.py
  │    └─ Assembles dict from ProvisionResult + RunResult + TeardownResult
  │
  ├─ print_summary(report)                     ← reporter.py (Rich table to terminal)
  ├─ save_json(report, "reports/")             ← reporter.py (if --json-report)
  └─ save_html(report, "reports/")             ← reporter.py (if --html-report)
```

### The Result Dataclasses

Each phase of the pipeline produces a typed result object (using Python `@dataclass`):

```python
@dataclass
class ProvisionResult:
    success: bool          # Did Terraform apply succeed?
    provider: str          # "aws", "gcp", "azure"
    lab_name: str          # From the spec
    outputs: dict          # Terraform outputs (public_ip, vpc_id, etc.)
    error: str | None      # Error message if failed
    elapsed_seconds: float # How long it took

@dataclass
class SuiteResult:         # One per test file
    suite_path: str        # Path to the test file
    passed: int            # Count from pytest output
    failed: int
    errors: int
    skipped: int
    exit_code: int         # 0 = all passed, 1 = failures

@dataclass
class RunResult:           # Aggregate of all suites
    lab_name: str
    suites: list[SuiteResult]
    elapsed_seconds: float

@dataclass
class TeardownResult:
    success: bool
    lab_name: str
    provider: str
    elapsed_seconds: float
    error: str | None
```

### The Provisioner Pattern (Strategy Pattern)

`provisioner.py` uses the **Strategy design pattern**:

```python
class BaseProvisioner:        # Abstract base — defines the interface
    def provision(spec) → ProvisionResult: ...
    def get_outputs(spec) → dict: ...

class AWSProvisioner(BaseProvisioner):    # Concrete — real implementation
    def provision(spec): ... # calls terraform + boto3

class GCPProvisioner(BaseProvisioner):   # Stub — placeholder
    def provision(spec): return ProvisionResult(success=False, error="not implemented")

# Registry — maps enum value to class
_REGISTRY = {CloudProvider.aws: AWSProvisioner, CloudProvider.gcp: GCPProvisioner}

def get_provisioner(provider) → BaseProvisioner:
    return _REGISTRY[provider]()  # cli.py doesn't care which one it gets
```

This means `cli.py` never says `if provider == "aws": ...` — it just calls `provisioner.provision(spec)` and the right implementation runs. Adding GCP support in Phase 3 means writing `GCPProvisioner.provision()` and changing nothing else.

### How Terraform Outputs flow into Tests

This is one of the most important connections in the system:

```
terraform output -json
  → {"public_ip": {"value": "54.123.45.67"}, "vpc_id": {"value": "vpc-abc123"}}

provisioner.get_outputs() parses this to:
  → {"public_ip": "54.123.45.67", "vpc_id": "vpc-abc123"}

runner._build_env() converts to environment variables:
  → CLOUDFORGE_PUBLIC_IP = "54.123.45.67"
  → CLOUDFORGE_VPC_ID    = "vpc-abc123"
  → CLOUDFORGE_LAB_NAME  = "my-test-lab"
  → CLOUDFORGE_REGION    = "us-east-1"

test_connectivity.py reads these at module level:
  → LAB_HOST = os.getenv("CLOUDFORGE_PUBLIC_IP")  # "54.123.45.67"

test_ssh_port_reachable() then:
  → socket.create_connection(("54.123.45.67", 22))  # Tests the REAL provisioned IP
```

The test files never hardcode IPs. They receive them dynamically from the provisioner via environment variables.

---

## 6. Phase 1 — Project Scaffold & Full Lifecycle

### Goal

Build the complete skeleton of the project: all files, all commands, working end-to-end pipeline, AWS provisioner, smoke tests, report generation.

### What Phase 1 Built

#### `cloudforge/schema.py` (Phase 1 version)

Phase 1 had a rich **nested schema** designed for maximum configurability:

```python
class LabSpec(BaseModel):
    name: str
    provider: CloudProvider
    description: str
    instance: InstanceSpec        # nested: type, count, ami, region, tags
    network: NetworkSpec          # nested: vpc_cidr, subnets, nat_gateway
    storage: StorageSpec | None   # nested: bucket_name, size_gb, type
    tests: list[TestSuiteSpec]    # nested list: each with path, markers, timeout, env_vars
    lifecycle: LifecycleSpec      # nested: on_provision hooks, on_teardown hooks, auto_teardown
    labels: dict[str, str]
```

The corresponding YAML looked like:
```yaml
name: demo-smoke-lab
provider: aws
instance:
  type: t3.micro
  count: 1
  region: us-east-1
network:
  vpc_cidr: "10.0.0.0/16"
  public_subnets: ["10.0.1.0/24"]
tests:
  - path: tests/smoke/test_connectivity.py
    markers: [smoke]
    timeout_seconds: 120
lifecycle:
  on_provision: ["echo 'ready'"]
  auto_teardown: true
```

#### `cloudforge/cli.py`

Five commands registered on a Click group:

```python
@click.group()
def cli(): ...             # The root group — `cloudforge`

@cli.command()
def run(): ...             # Full lifecycle

@cli.command()
def provision(): ...       # Provision only

@cli.command()
def test(): ...            # Test only

@cli.command()
def destroy(): ...         # Destroy only

@cli.command()
def validate(): ...        # Validate spec only
```

#### `cloudforge/provisioner.py`

- `AWSProvisioner`: writes a `.tfvars.json`, runs `terraform init` then `terraform apply`, reads back outputs with `terraform output -json`, queries EC2 via boto3
- `GCPProvisioner`: stub returning failure
- `AzureProvisioner`: stub returning failure
- `get_provisioner()`: factory function that returns the right class based on the provider enum

#### `cloudforge/runner.py`

- Accepts `list[TestSuiteSpec]` — each suite had its own path, markers, timeout, and env_vars
- Spawned `pytest` as a subprocess for each suite
- Parsed pass/fail counts from pytest's stdout output
- Built environment variables from Terraform outputs + suite-specific env_vars

#### `cloudforge/teardown.py`

- Ran `on_teardown` lifecycle hooks (shell commands) before destroying
- Located the correct Terraform directory by provider
- Ran `terraform destroy -auto-approve`
- Cleaned up the `.tfvars.json` file

#### `cloudforge/reporter.py`

- `build_report()` — assembles a structured `dict` from all three result objects
- `save_json()` — writes `reports/report_<lab>_<timestamp>.json`
- `save_html()` — writes `reports/report_<lab>_<timestamp>.html` using an inline HTML template
- `print_summary()` — prints a Rich table to the terminal showing each phase's status

#### `terraform/aws/main.tf`

Full AWS infrastructure in one file:

| Resource | AWS Name | Purpose |
|---|---|---|
| `aws_vpc` | VPC | Isolated network for the lab |
| `aws_internet_gateway` | IGW | Connects VPC to the internet |
| `aws_subnet` | Public Subnet | Where EC2 instances live |
| `aws_route_table` | Route Table | Routes `0.0.0.0/0` → IGW |
| `aws_route_table_association` | RT Association | Links subnet to route table |
| `aws_security_group` | SG | Firewall rules (SSH/HTTP/HTTPS in, all out) |
| `aws_instance` | EC2 | The actual lab server(s) |
| `data.aws_availability_zones` | AZ data | Queries which AZs exist in the region |

Outputs exposed: `instance_ids`, `public_ips`, `public_ip`, `vpc_id`, `region`, `lab_name`

#### `tests/smoke/test_connectivity.py`

Tests that run on the machine running CloudForge (not on the EC2 instance):

| Test | What it checks |
|---|---|
| `test_environment_variables_present` | At least one `CLOUDFORGE_*` host var is set |
| `test_ssh_port_reachable` | Port 22 accepts connections, returns SSH banner |
| `test_dns_resolves_for_host` | Host resolves via DNS |
| `test_http_endpoint_responds` | HTTP endpoint returns < 400 |
| `test_local_dns_resolution` | Local machine's DNS works (sanity check) |
| `test_outbound_http_connectivity` | Outbound internet access works |

#### `tests/smoke/test_api.py`

Two test classes:

**`TestAPIEndpoints`** — Tests against a REST API endpoint (if `CLOUDFORGE_API_ENDPOINT` is set):
- `/health` or `/healthz` returns 200
- Root returns valid JSON
- Response time under 5 seconds

**`TestAWSMetadata`** — Tests EC2 Instance Metadata Service v2 (IMDSv2):
- Fetches an IMDSv2 token (requires a PUT request with a TTL header — security improvement over v1)
- Uses that token to read the instance ID
- Verifies `CLOUDFORGE_LAB_NAME` and `CLOUDFORGE_REGION` were injected

---

## 7. Phase 2 — Schema Redesign with Pydantic v2

### Goal

Replace the nested schema with a flat, minimal schema matching a specific YAML format. Apply all Pydantic v2 validation best practices.

### The New Canonical YAML Format

```yaml
name: my-test-lab
provider: aws
region: us-east-1
instance_type: t2.micro
storage_gb: 10
tags:
  project: cloudforge
  env: test
tests:
  - connectivity
  - api
  - performance
teardown_on_success: true
teardown_on_failure: false
```

### The New `LabSpec` Model

```python
class LabSpec(BaseModel):
    name: str
    provider: CloudProvider                                    # enum: aws | gcp | azure
    region: str = "us-east-1"
    instance_type: Annotated[str, Field(min_length=1)]        # non-empty enforced by Field
    storage_gb: Annotated[int, Field(ge=1, le=100)] = 20      # 1-100 enforced by Field
    tags: dict[str, str] = Field(default_factory=dict)
    tests: Annotated[list[str], Field(min_length=1)]           # at least 1 item
    teardown_on_success: bool = True
    teardown_on_failure: bool = False
```

### All Four Validations — How They Work

#### 1. `provider` — must be `aws | gcp | azure`

```python
class CloudProvider(str, Enum):
    aws = "aws"
    gcp = "gcp"
    azure = "azure"

provider: CloudProvider
```

When Pydantic sees `provider: "aws"` in the YAML, it calls `CloudProvider("aws")`. If the value is `"docker"` or `"k8s"`, it raises:
```
provider: Input should be 'aws', 'gcp' or 'azure' [type=enum]
```

Making `CloudProvider` inherit from `str` means `spec.provider == "aws"` works — it's both a string and an enum simultaneously.

#### 2. `instance_type` — non-empty string

Two layers of protection:

```python
instance_type: Annotated[str, Field(min_length=1)]  # Layer 1: rejects ""

@field_validator("instance_type")
@classmethod
def instance_type_not_blank(cls, v: str) -> str:
    if not v.strip():               # Layer 2: rejects "   " (whitespace only)
        raise ValueError("instance_type must be a non-empty string")
    return v
```

`Field(min_length=1)` catches empty string `""`. The `@field_validator` catches strings like `"   "` that pass the length check but are meaningless.

#### 3. `storage_gb` — between 1 and 100

```python
storage_gb: Annotated[int, Field(ge=1, le=100)] = 20
```

`ge` = "greater than or equal to", `le` = "less than or equal to". Pydantic raises:
```
storage_gb: Input should be greater than or equal to 1 [type=greater_than_equal]
storage_gb: Input should be less than or equal to 100 [type=less_than_equal]
```

#### 4. `tests` — list with at least one item, no blank names

```python
tests: Annotated[list[str], Field(min_length=1)]  # Layer 1: list must not be empty

@field_validator("tests")
@classmethod
def tests_not_empty(cls, v: list[str]) -> list[str]:
    if not v:                               # Layer 2: redundant safety check
        raise ValueError("tests must contain at least one item")
    blanks = [t for t in v if not t.strip()]   # Layer 3: no blank test names
    if blanks:
        raise ValueError(f"test names must be non-empty strings, got: {blanks}")
    return v
```

### The `load_spec()` Function

```python
def load_spec(path: str) -> LabSpec:
    with open(path) as fh:
        raw = yaml.safe_load(fh)    # YAML → dict
    return LabSpec.model_validate(raw)  # dict → LabSpec (with full validation)
```

This is the **boundary function** — the single point where unvalidated YAML from disk becomes a fully validated, type-safe Python object. Everything downstream receives a `LabSpec` and can trust all fields are valid.

### Changes That Rippled Into Other Files

#### `provisioner.py` — `_write_var_file()`

Phase 1 called `spec.to_terraform_vars()` — a method on the model that built the dict.  
Phase 2 builds it inline since the flat spec makes it straightforward:

```python
# Phase 1:
var_file.write_text(json.dumps(spec.to_terraform_vars(), indent=2))

# Phase 2:
vars_ = {
    "lab_name": spec.name,
    "region": spec.region,            # was: spec.instance.region
    "instance_type": spec.instance_type,  # was: spec.instance.type
    "instance_count": 1,              # hardcoded — flat spec has no count field
    "tags": {**spec.tags, "ManagedBy": "cloudforge", "Lab": spec.name},
}
var_file.write_text(json.dumps(vars_, indent=2))
```

#### `runner.py` — test name resolution

Phase 1: `spec.tests` was `list[TestSuiteSpec]` — each item had `.path`, `.markers`, `.timeout_seconds`, `.env_vars`.  
Phase 2: `spec.tests` is `list[str]` — just names. A lookup dict maps names to paths:

```python
_TEST_PATH_MAP = {
    "connectivity": "tests/smoke/test_connectivity.py",
    "api":          "tests/smoke/test_api.py",
    "performance":  "tests/smoke/test_performance.py",
}

def _resolve_path(test_name: str) -> str:
    return _TEST_PATH_MAP.get(test_name.lower(), test_name)
    # Falls back to the name itself — lets users pass actual file paths too
```

#### `teardown.py` — removed lifecycle hooks

Phase 1 ran `on_teardown` shell hooks before destroying:
```python
for hook in spec.lifecycle.on_teardown:
    subprocess.run(hook, shell=True)
```
Phase 2's flat schema has no `lifecycle` field → the hook loop was deleted. The `_run_hook()` helper function was also removed since nothing called it.

#### `cli.py` — teardown decision logic

Phase 1 used `spec.lifecycle.auto_teardown` and `spec.lifecycle.teardown_on_failure`.  
Phase 2 uses the flat fields directly:

```python
# Phase 1:
should_teardown = (
    not no_teardown
    and spec.lifecycle.auto_teardown
    and (provision_result.success or spec.lifecycle.teardown_on_failure)
    and (run_result is None or run_result.success or spec.lifecycle.teardown_on_failure)
)

# Phase 2 (cleaner logic):
tests_ok = run_result is None or run_result.success
overall_ok = provision_result.success and tests_ok
should_teardown = not no_teardown and (
    (overall_ok and spec.teardown_on_success)     # success path
    or (not overall_ok and spec.teardown_on_failure)  # failure path
)
```

---

## 8. Phase 1 vs Phase 2 — What Changed and Why

### Schema: Nested → Flat

| Aspect | Phase 1 | Phase 2 |
|---|---|---|
| Model count | 6 classes (LabSpec + 5 sub-models) | 2 classes (LabSpec + CloudProvider enum) |
| tests field type | `list[TestSuiteSpec]` (objects) | `list[str]` (names) |
| teardown config | Under `lifecycle.auto_teardown` + `lifecycle.teardown_on_failure` | Top-level `teardown_on_success` + `teardown_on_failure` |
| Region | Under `instance.region` | Top-level `region` |
| Instance type | Under `instance.type` | Top-level `instance_type` |
| Hooks | `lifecycle.on_provision`, `lifecycle.on_teardown` | Not in spec |

### Why the schema shrank

The Phase 2 spec format (given as a requirement) is deliberately simpler — it targets the common case where you just want to spin up a single instance, run named test suites, and tear down. The rich nested structure of Phase 1 was forward-looking scaffolding for things like:
- Multiple subnets with different CIDRs
- Per-suite test markers and timeouts  
- Custom shell hooks before/after provisioning

These features will come back in later phases when the requirements call for them. The rule: **only validate what the spec actually contains**.

### Lines of code comparison

| File | Phase 1 | Phase 2 | Change |
|---|---|---|---|
| `schema.py` | 88 lines | 52 lines | −36 (nested models removed) |
| `runner.py` | 156 lines | 159 lines | +3 (path mapping added) |
| `teardown.py` | 93 lines | 76 lines | −17 (hook loop removed) |
| `cli.py` | 138 lines | 134 lines | −4 (cleaner teardown logic) |
| `provisioner.py` | 158 lines | 165 lines | +7 (inline var building) |

Total: 189 lines removed, 102 lines added. Net reduction of 87 lines — because the requirements became more precise.

---

## 9. Key Concepts & Terminology Dictionary

### Infrastructure as Code (IaC)
Defining cloud infrastructure in code files (`.tf`, `.yaml`, `.json`) rather than clicking through a web console. Benefits: reproducible, version-controlled, peer-reviewable, automated.

### AMI (Amazon Machine Image)
A snapshot of an operating system disk. When you launch an EC2 instance, you choose an AMI — it determines what OS and pre-installed software the instance boots with. `ami-0c02fb55956c7d316` is Amazon Linux 2023 in `us-east-1`.

### VPC (Virtual Private Cloud)
An isolated network within AWS. Think of it as your private data center's network, but in the cloud. All EC2 instances must live inside a VPC.

### Subnet
A subdivision of a VPC's IP address range. Public subnets have a route to the Internet Gateway (instances get public IPs). Private subnets don't (instances can only be reached from within the VPC).

### Security Group (SG)
A stateful firewall attached to EC2 instances. Defines what traffic is allowed in (ingress) and out (egress). CloudForge's SG opens ports 22 (SSH), 80 (HTTP), 443 (HTTPS) for inbound.

### Internet Gateway (IGW)
The component that connects a VPC to the internet. Without an IGW, no traffic can flow in or out of the VPC.

### Route Table
A set of routing rules. CloudForge creates a route `0.0.0.0/0 → IGW` meaning "send all internet-bound traffic through the IGW."

### Terraform State
Terraform keeps a `terraform.tfstate` file that maps your config to actual cloud resources. When you run `terraform destroy`, it reads state to know which resources to delete. This is why you never delete `.tfstate` manually.

### `terraform init`
Downloads the provider plugins (e.g., `hashicorp/aws ~> 5.0`) into `.terraform/`. Must be run before `apply` or `destroy`.

### `terraform apply`
Creates or updates resources to match the `.tf` config. `-auto-approve` skips the manual "yes" prompt.

### `terraform destroy`
Deletes all resources tracked in state. `-auto-approve` skips the prompt.

### `terraform output -json`
Prints all declared `output` blocks as JSON. CloudForge parses this to get IPs and IDs to inject into tests.

### EC2 (Elastic Compute Cloud)
AWS's virtual server service. A running EC2 instance is a virtual machine in AWS's datacenter.

### IMDSv2 (Instance Metadata Service v2)
A secure endpoint (`http://169.254.169.254/...`) accessible only from within an EC2 instance. It provides metadata about the instance (ID, region, IAM role). v2 requires a PUT request to get a token first — preventing SSRF attacks that could steal credentials.

### Smoke Tests
A minimal set of tests that verify "is the system alive?" — not exhaustive functional testing. If smoke tests fail, there's no point running the full test suite. Named after the practice of turning on a circuit and checking if it smokes.

### Subprocess
Running an external program from within Python. CloudForge uses `subprocess.run()` to invoke `terraform` and `python -m pytest` — treating them as black-box tools.

### Pydantic `@field_validator`
A class method that validates a specific field's value after Pydantic parses it. Must be decorated with `@classmethod` in v2. Returns the (potentially modified) value or raises `ValueError`.

### `Annotated[type, Field(...)]`
Python's `Annotated` type lets you attach metadata to a type without changing it. `Annotated[int, Field(ge=1, le=100)]` means "an int, but with Pydantic constraints ge=1 and le=100." The `Field()` call is metadata consumed by Pydantic; the type itself is still just `int`.

### Dataclass
Python's `@dataclass` decorator auto-generates `__init__`, `__repr__`, and `__eq__` from class-level field annotations. Used for result objects (`ProvisionResult`, `RunResult`, `SuiteResult`, `TeardownResult`) because they're plain data containers — no custom validation needed.

### Strategy Pattern
A design pattern where you define a base interface and multiple interchangeable implementations. `BaseProvisioner` is the interface; `AWSProvisioner`, `GCPProvisioner`, `AzureProvisioner` are strategies. The caller (`cli.py`) uses whichever strategy `get_provisioner()` returns without knowing the details.

### Registry Pattern
A dictionary mapping keys to classes/functions. `_REGISTRY = {CloudProvider.aws: AWSProvisioner}` maps the enum value to the class. `get_provisioner()` looks up the right class at runtime.

### `str | None`
Python 3.10+ union type syntax. Means "a string or None." Same as `Optional[str]` from `typing`. Used for fields that may be absent (`error: str | None = None`).

### `from __future__ import annotations`
Enables PEP 563 — all annotations in the file are treated as strings and evaluated lazily. This allows forward references (a class referencing itself before it's fully defined) and makes type hints faster since they're not evaluated at import time.

### `time.monotonic()`
A clock that only moves forward, never backward. Used for measuring elapsed time. Unlike `time.time()`, it's not affected by system clock adjustments (DST, NTP sync). Always use `monotonic()` for durations.

---

## 10. Design Decisions & Trade-offs

### Why subprocess for Terraform instead of the Terraform Python SDK?

There is a `python-terraform` library, but it's unmaintained. The official way to drive Terraform programmatically is via its CLI. Using `subprocess.run()` with `capture_output=True` gives us full control over args, working directory, timeout, and output parsing — without third-party risk.

### Why parse pytest stdout instead of using `pytest`'s Python API?

pytest's public Python API (`pytest.main()`) is primarily for plugin authors and shares the same process. Running pytest as a subprocess:
1. Isolates failures — a segfault in a test doesn't crash CloudForge
2. Captures all output cleanly via `capture_output=True`
3. Allows setting `env=` on the subprocess, which is how we inject `CLOUDFORGE_*` variables
4. Mirrors how a human would run tests on the command line

### Why Rich instead of logging?

`logging` is designed for application logs (structured, leveled, file-output). Rich is designed for interactive terminal UIs. CloudForge is a CLI tool a human watches in real time — colored status, tables, and progress output are more useful than log levels.

### Why `@dataclass` for results but `BaseModel` for the spec?

| | `BaseModel` | `@dataclass` |
|---|---|---|
| Validation | Yes — at construction time | No |
| JSON serialization | Built-in (`model_dump()`) | Needs `dataclasses.asdict()` |
| Immutable by default | Yes | No |
| Use case | External input (YAML spec) | Internal data passing |

The spec comes from the outside world (a file a user wrote) — validation is essential. Result objects are created internally by code we control — validation would just be overhead.

### Why `teardown_on_success` and `teardown_on_failure` as separate booleans?

Four states in a 2x2 matrix:

| Scenario | `teardown_on_success=true` | `teardown_on_success=false` |
|---|---|---|
| `teardown_on_failure=true` | Always teardown | Only teardown on failure |
| `teardown_on_failure=false` | Only teardown on success | Never teardown |

This gives maximum control without a complex teardown policy enum. The default `(true, false)` is the safe default: clean up after success, but leave the environment alive after failure so you can debug.

### Why stubs for GCP and Azure in Phase 1?

The `_REGISTRY` + `BaseProvisioner` pattern means the CLI works without GCP/Azure implemented. Calling `cloudforge run lab.yaml` with `provider: gcp` returns a clear error ("GCP not implemented") rather than crashing. This is better UX and forces the clean interface to be designed upfront — you can't implement GCP without implementing `provision()` and `get_outputs()`.

---

*Last updated: Phase 2 — May 2026*  
*Repository: https://github.com/shashank8walke/cloudforge*

---

# CloudForge — Phases 3 – 6 Reference

> This section continues the Phase 1 & 2 reference above.  
> Phases 3–6 build on each other: real AWS provisioning (3), production Terraform (4),
> fixture-based smoke tests (5), and a fully polished CLI (6).

---

## 11. Phase 3 — Direct boto3 AWS Provisioner (no Terraform)

### Goal

Replace the Terraform-subprocess approach inside `AWSProvisioner` with **direct AWS API calls** via boto3. This removes the Terraform dependency from the provision path, gives instant feedback, and makes the code easier to unit-test with `moto` (AWS mocking library).

### Why replace Terraform in the provisioner?

| Concern | Terraform subprocess | Direct boto3 |
|---|---|---|
| Speed | ~60 s (init + apply) | ~30–90 s (waiter-gated) |
| Output parsing | Parse JSON from stdout | Native Python dict |
| Error handling | Parse stderr text | `ClientError` exception |
| Unit testing | Hard — needs Terraform binary | Easy — `moto` patches boto3 |
| State tracking | `.tfstate` file | `self.resources` dict |

### What Changed

#### `cloudforge/provisioner.py` — full rewrite

**`BaseProvisioner`** interface simplified to three methods:
```python
def provision(self) -> dict:   raise NotImplementedError
def get_status(self) -> str:   raise NotImplementedError
def tag_resources(self, resources: dict) -> None: raise NotImplementedError
```
The `spec` is now stored at `__init__` time (`self.spec = spec`) so `provision()` takes no arguments — the provisioner is bound to one spec.

**`AWSProvisioner.__init__`** creates the two boto3 clients up front:
```python
self._ec2 = boto3.client("ec2", region_name=spec.region)
self._s3  = boto3.client("s3",  region_name=spec.region)
```

**`AWSProvisioner.provision()`** — four private methods called in sequence:
```python
self._launch_ec2()       # run_instances → stores instance_id
self._wait_for_running() # get_waiter("instance_running"), Delay=5, MaxAttempts=40
self._fetch_public_ip()  # describe_instances → stores public_ip
self._create_s3_bucket() # create_bucket → stores s3_bucket name
self.tag_resources(self.resources)
```

**`_create_s3_bucket()`** — name pattern: `cloudforge-{spec.name}-{uuid4().hex[:8]}`.  
Important: `us-east-1` must **not** include `CreateBucketConfiguration.LocationConstraint` — AWS rejects it.

```python
if self.spec.region == "us-east-1":
    self._s3.create_bucket(Bucket=bucket_name)
else:
    self._s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": self.spec.region},
    )
```

**`_DEFAULT_AMI = "ami-0c02fb55956c7d316"`** — Amazon Linux 2 in `us-east-1`. Other regions require their own AMI IDs.

**`tag_resources()`** — merges spec tags with `{"ManagedBy": "cloudforge", "Lab": spec.name}`. Uses `create_tags` for EC2 and `put_bucket_tagging` for S3. Non-fatal: logs a yellow warning on `ClientError` rather than raising, so a tagging hiccup never blocks provisioning.

**`get_status()`** — calls `describe_instances` and returns the `State.Name` string (`"running"`, `"stopped"`, `"terminated"`). Returns `"not_provisioned"` if `self.resources` has no `instance_id`. Returns `"error: <Code>"` on `ClientError`.

#### `cloudforge/cli.py` — `_run_provision()` helper

Because `provisioner.provision()` now returns a raw `dict` (not a `ProvisionResult`), the CLI wraps it:

```python
def _run_provision(provisioner, spec) -> ProvisionResult:
    start = time.monotonic()
    try:
        outputs = provisioner.provision()   # dict
        return ProvisionResult(success=True, outputs=outputs, ...)
    except ClientError as exc:
        return ProvisionResult(success=False, error=f"{code}: {msg}", ...)
    except NotImplementedError as exc:
        return ProvisionResult(success=False, error=str(exc), ...)
```

This keeps `reporter.py` working (it still receives `ProvisionResult`) while the provisioner API is clean.

### `get_provisioner()` signature change

```python
# Phase 1 (old)
get_provisioner(provider: CloudProvider) -> BaseProvisioner  # caller passes spec later
# Phase 3 (new)
get_provisioner(provider: CloudProvider, spec: LabSpec) -> BaseProvisioner  # spec bound at construction
```

The provisioner is now bound to a spec from the start — no spec argument needed on `provision()`.

### Key boto3 Concepts

| API call | What it does |
|---|---|
| `run_instances(ImageId, InstanceType, MinCount=1, MaxCount=1, TagSpecifications=[...])` | Launch one EC2 instance; returns instance ID immediately |
| `get_waiter("instance_running").wait(InstanceIds=[id], WaiterConfig={Delay, MaxAttempts})` | Poll every 5 s until state == running (up to 40 attempts = 200 s) |
| `describe_instances(InstanceIds=[id])` | Returns full instance metadata including `PublicIpAddress` |
| `create_bucket(Bucket=name)` | Create S3 bucket; `us-east-1` omits `LocationConstraint` |
| `put_bucket_tagging(Bucket, Tagging={"TagSet":[...]})` | Apply key-value tags to an S3 bucket |
| `botocore.exceptions.ClientError` | All AWS API errors — check `exc.response["Error"]["Code"]` |

---

## 12. Phase 4 — Production Terraform Configs (AWS + GCP)

### Goal

Replace the stub/draft Terraform files from Phase 1 with **production-ready, fully parameterised** configurations for both AWS and GCP. Also introduce a canonical shared `variables.tf` that documents every input variable across both modules.

### File Structure After Phase 4

```
terraform/
├── aws/
│   └── main.tf          ← Full AWS config: EC2, S3, security group, outputs
├── gcp/
│   └── main.tf          ← Full GCP config: Compute Engine, Cloud Storage, outputs
└── variables.tf         ← Canonical variable documentation (shared reference)
```

### `terraform/aws/main.tf` — Key Design Decisions

**Providers pinned:**
```hcl
required_providers {
  aws    = { source = "hashicorp/aws",    version = "~> 5.0" }
  random = { source = "hashicorp/random", version = "~> 3.6" }
}
```
`~> 5.0` means "5.x but not 6.x" — patch updates are accepted, major versions are not.

**`locals` block for tag merging:**
```hcl
locals {
  common_tags = merge(var.tags, {
    Project   = var.project_name
    ManagedBy = "cloudforge"
    Provider  = "aws"
  })
}
```
Merging means user-provided tags and CloudForge standard tags coexist. If the user provides a `Project` tag, `merge()` lets the standard one win (rightmost wins in HCL `merge()`).

**`random_id` for bucket uniqueness:**
```hcl
resource "random_id" "bucket_suffix" {
  byte_length = 4
  keepers = { project_name = var.project_name }
}
```
`keepers` means the random ID is only regenerated when `project_name` changes — not on every `terraform apply`. This prevents accidental bucket deletion on re-apply.

**S3 public access block:**
```hcl
resource "aws_s3_bucket_public_access_block" "lab" {
  bucket                  = aws_s3_bucket.lab.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```
Best practice: always block public access unless explicitly needed.

**Outputs:**
```hcl
output "instance_id" { value = aws_instance.lab.id }
output "public_ip"   { value = aws_instance.lab.public_ip }
output "bucket_name" { value = aws_s3_bucket.lab.id }
```

### `terraform/gcp/main.tf` — Key Differences from AWS

GCP uses a different terminology:

| AWS concept | GCP equivalent |
|---|---|
| EC2 instance | `google_compute_instance` |
| Instance type (e.g., `t2.micro`) | Machine type (e.g., `f1-micro`) |
| AMI | Boot disk image (e.g., `debian-cloud/debian-11`) |
| S3 bucket | `google_storage_bucket` |
| Tags | Labels (lowercase keys + values, dashes only) |
| Region | Region (but GCS location must be UPPERCASE) |

**Critical GCP constraints:**
- Labels must be lowercase: `managed_by = "cloudforge"` not `ManagedBy`
- `google_storage_bucket` location must be uppercase: `location = upper(var.region)` converts `us-central1` → `US-CENTRAL1`
- `force_destroy = false` — prevents accidental bucket deletion with objects in it (Terraform would error, which is safer)

**locals for GCP:**
```hcl
locals {
  common_labels = merge(var.tags, {
    project    = lower(var.project_name)
    managed_by = "cloudforge"
    provider   = "gcp"
  })
}
```

### `terraform/variables.tf` — Shared Variable Reference

This file is not used by Terraform directly (each module has its own variable declarations). It is a **human-readable canonical reference** that documents:
- Which variables are universal (both AWS and GCP)
- Which are AWS-specific
- Which are GCP-specific
- Validation rules (e.g., `project_name` matches `^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$`)

```hcl
variable "project_name" {
  description = "Project name used in resource names and labels. Must be lowercase."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-32 chars, lowercase letters/numbers/dashes only."
  }
}
```

### Why `random_id` instead of a timestamp?

A timestamp like `${formatdate("YYYYMMDDHHmmss", timestamp())}` regenerates on every `apply`, meaning Terraform would try to recreate the bucket every time — which fails if the bucket already exists. `random_id` with `keepers` only regenerates when the keeper value changes.

---

## 13. Phase 5 — Fixture-Based Smoke Test Suite with conftest.py

### Goal

Replace ad-hoc environment-variable-based test setup with a **pytest fixture chain** rooted in `.cloudforge_state.json`. All test functions receive typed, validated fixtures instead of reading `os.environ` directly.

### The Problem with Environment Variables

Phase 1 tests used:
```python
LAB_HOST = os.getenv("CLOUDFORGE_PUBLIC_IP", "")

@pytest.mark.skipif(not LAB_HOST, reason="no public IP")
def test_ssh_port_reachable():
    socket.create_connection((LAB_HOST, 22))
```

Problems:
1. Every test file had its own `os.getenv` calls — duplicated fragile boilerplate
2. Skip conditions were at the function level — hard to centralise
3. No guarantee the state file was valid before tests started
4. Hard to extend with new resource types (would need new env vars in every file)

### The Solution: `conftest.py` with session-scoped fixtures

`tests/smoke/conftest.py` defines a **fixture chain**. pytest auto-discovers `conftest.py` and makes all fixtures in it available to every test in the `tests/smoke/` directory.

```
resources (session) ← reads .cloudforge_state.json
    │
    ├─ instance_ip (session)  ← resources["public_ip"]
    ├─ instance_id (session)  ← resources["instance_id"]
    ├─ bucket_name (session)  ← resources["s3_bucket"]
    └─ aws_region  (session)  ← resources["region"] (default: "us-east-1")
```

**`scope="session"`** means each fixture is evaluated **once per pytest run** — not once per test. This is crucial: you don't want to re-read and re-validate the JSON file 7 times for 7 tests.

**Skip propagation:** `pytest.skip()` inside a session fixture causes every test that depends on that fixture (directly or indirectly) to be skipped with the same message. So if the state file is missing, all 7 tests are skipped cleanly — no `KeyError` traceback, no misleading FAILED status.

```python
@pytest.fixture(scope="session")
def resources() -> dict:
    if not _STATE_FILE.exists():
        pytest.skip(f"State file '{_STATE_FILE}' not found. Run cloudforge provision first.")
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.skip(f"State file is not valid JSON: {exc}")
    return data

@pytest.fixture(scope="session")
def instance_ip(resources: dict) -> str:
    ip = resources.get("public_ip", "")
    if not ip:
        pytest.skip("'public_ip' not found in state file")
    return ip
```

### The `.cloudforge_state.json` State File

Written by `AWSProvisioner._write_state_file()` after a successful `provision()` call:

```json
{
  "instance_id": "i-0abc123def456789",
  "public_ip": "54.123.45.67",
  "s3_bucket": "cloudforge-my-test-lab-a1b2c3d4",
  "launch_time": 47.83,
  "region": "us-east-1"
}
```

- `launch_time` — total seconds from `time.monotonic()` start to waiter completion
- `region` — copied from `spec.region` so tests know which region without re-reading the spec
- Listed in `.gitignore` — contains live resource IDs; never commit

### New Test Files

#### `tests/smoke/test_connectivity.py` (rewritten)

Tests that use **`instance_ip`** and **`bucket_name`** fixtures:

| Test | Fixture | What it does |
|---|---|---|
| `test_ssh_port_open` | `instance_ip` | TCP connect to port 22, 3s timeout |
| `test_http_port_open` | `instance_ip` | TCP connect to port 80, 3s timeout |
| `test_s3_bucket_exists` | `bucket_name` | `head_bucket()` — 404 vs 403 distinction |

**`_tcp_probe(host, port, timeout)`** distinguishes three failure modes:
- `socket.timeout` → firewall/security group blocking the port
- `ConnectionRefusedError` → port reached but no daemon listening
- `OSError` → general network failure (routing, DNS)

#### `tests/smoke/test_api.py` (rewritten)

| Test | Fixtures | What it does |
|---|---|---|
| `test_aws_describe_instance` | `instance_id`, `aws_region` | `describe_instances()` asserts `State.Name == "running"` |
| `test_s3_put_get` | `bucket_name` | PUT → GET → assert body matches → DELETE in `finally` |

`test_s3_put_get` uses `uuid.uuid4()` for the key to avoid collision across parallel runs. The DELETE is in a `finally` block so cleanup always happens even if the GET assertion fails.

#### `tests/smoke/test_performance.py` (new)

| Test | Fixture | Threshold | What it does |
|---|---|---|---|
| `test_instance_launch_time` | `resources` | < 300 s | Reads `launch_time` from state dict; skips if key absent |
| `test_s3_latency` | `bucket_name` | < 2.0 s | Times a 1 KB PUT; DELETE in finally (not timed) |

Why skip (not fail) if `launch_time` is absent? Older state files (from before Phase 5) won't have this key. Skipping is honest — the test simply can't run — while failing would be misleading.

### `provisioner.py` additions

```python
# In provision() after tag_resources():
elapsed = time.monotonic() - start
self.resources["launch_time"] = round(elapsed, 2)
self.resources["region"]      = self.spec.region
self._write_state_file()

def _write_state_file(self) -> None:
    state_path = Path(".cloudforge_state.json")
    state_path.write_text(
        json.dumps(self.resources, indent=2, default=str),
        encoding="utf-8",
    )
```

`default=str` in `json.dumps` handles any non-serialisable types (e.g., `datetime`) by converting to string — defensive coding.

### pytest `pytestmark`

```python
pytestmark = pytest.mark.smoke
```

At module level in each test file. This applies the `smoke` marker to every test in the file without decorating each function individually. You can then run only smoke tests with:
```bash
pytest -m smoke
```

---

## 14. Phase 6 — Polished CLI (--spec flags, --dry-run, boto3 teardown, JSON report)

### Goal

Make the CLI production-ready:
1. Consistent `--spec` named option across all commands
2. `--dry-run` for `provision` — preview without touching AWS
3. Rich table output for every command
4. `teardown` command using boto3 (not Terraform)
5. `cloudforge run` always writes `cloudforge_report.json`
6. `validate` shows full spec in a table

### CLI Command Reference (Phase 6 Final)

| Command | Key flags | What it does |
|---|---|---|
| `cloudforge provision --spec lab.yaml` | `--dry-run` | Provision lab; print resource table; save state file |
| `cloudforge test --spec lab.yaml` | — | Load state file; run pytest suites; print pass/fail table |
| `cloudforge teardown --spec lab.yaml` | — | Terminate EC2, delete S3, remove state file via boto3 |
| `cloudforge run --spec lab.yaml` | `--no-teardown`, `--json-report`, `--html-report` | Full lifecycle; always writes `cloudforge_report.json` |
| `cloudforge validate --spec lab.yaml` | — | Validate YAML spec; print field table; exit 0/1 |

### Why `--spec` instead of a positional argument?

Phase 1–5 used positional args: `cloudforge provision examples/lab.yaml`.  
Phase 6 changes to named options: `cloudforge provision --spec examples/lab.yaml`.

Reasons:
- **Explicit over implicit** — `--spec` makes it clear what the file *is*; a bare path is ambiguous
- **Shell tab completion** — Click's option completion works better than bare argument completion
- **CI readability** — `--spec "$SPEC_FILE"` is self-documenting in pipeline YAML
- **Extensibility** — future options like `--override region=eu-west-1` need the arg to be named to avoid positional ordering ambiguity

### `provision --dry-run`

```
cloudforge provision --spec examples/lab.yaml --dry-run
```

Prints a Rich "Planned Resources (Dry Run)" table:

| Resource | Planned Value |
|---|---|
| Provider | aws |
| Region | us-east-1 |
| EC2 Instance Type | t2.micro |
| Root Volume | 10 GB |
| S3 Bucket Name | cloudforge-my-test-lab-\<random8hex\> |
| EC2 Tags | project=cloudforge, env=test, ManagedBy=cloudforge, Lab=my-test-lab |
| State File | .cloudforge_state.json |

No AWS API calls are made. This lets you sanity-check what a spec will create before committing.

### `test` command — state file + Rich table

The `test` command now:
1. Calls `_load_state_file()` — exits 1 with a clear message if absent
2. Displays `instance_id` and `s3_bucket` from the state before running
3. Runs `run_suites()` (pytest as subprocess for each suite in spec)
4. Renders a Rich table with per-suite: name, passed, failed, skipped, duration, PASS/FAIL badge
5. Prints aggregate totals (total passed / failed across all suites)

```
┌──────────────────────────────────────────────┐
│               Test Results                   │
├──────────────────┬──────┬──────┬─────┬───────┤
│ Suite            │Passed│Failed│Skip │Status │
├──────────────────┼──────┼──────┼─────┼───────┤
│test_connectivity │  3   │  0   │  0  │ PASS  │
│test_api          │  2   │  0   │  0  │ PASS  │
│test_performance  │  2   │  0   │  0  │ PASS  │
└──────────────────┴──────┴──────┴─────┴───────┘
Tests: ALL PASSED
passed=7  failed=0  (12.4s)
```

### `teardown` — boto3 instead of Terraform

**Old approach (Phases 1–5):**
```python
subprocess.run(["terraform", "destroy", "-auto-approve", ...])
```
Requires Terraform installed, `.tfstate` to exist, working directory to be correct.

**New approach (Phase 6):**
```python
ec2.terminate_instances(InstanceIds=[instance_id])
waiter = ec2.get_waiter("instance_terminated")
waiter.wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})

paginator = s3.get_paginator("list_objects_v2")
for page in paginator.paginate(Bucket=bucket_name):
    s3.delete_objects(Bucket=bucket_name, Delete={"Objects": [...]})
s3.delete_bucket(Bucket=bucket_name)
```

**Why terminate first, then bucket?**
There's no hard dependency order here. Both are independent resources. We terminate EC2 first because it takes longer (waiter blocks for up to 5 minutes). S3 deletion is near-instant once the objects are emptied.

**Why empty the bucket before deleting?**
AWS requires a bucket to be empty before `delete_bucket()` succeeds. `list_objects_v2` is paginated (returns max 1000 objects per page) so the code paginates through all pages with a paginator.

**Non-fatal warnings:**
- `InvalidInstanceID.NotFound` → instance was already terminated; log warning, continue
- `NoSuchBucket` / HTTP 404 → bucket was already deleted; log warning, continue

**State file removal:**
On a clean teardown (no errors), `.cloudforge_state.json` is deleted. On partial failure, the file is retained so the operator can inspect which resource IDs still need manual cleanup.

### `run` — `cloudforge_report.json`

`cloudforge run` always writes `cloudforge_report.json` in the current working directory:
```python
_DEFAULT_REPORT = Path("cloudforge_report.json")
_DEFAULT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
```

The report contains the full lifecycle outcome:
```json
{
  "lab_name": "my-test-lab",
  "provider": "aws",
  "generated_at": "2026-05-22T10:30:00+00:00",
  "overall_success": true,
  "provision": { "success": true, "elapsed_seconds": 47.8, "outputs": {...} },
  "tests": { "success": true, "total_passed": 7, "total_failed": 0, "suites": [...] },
  "teardown": { "success": true, "elapsed_seconds": 62.3 }
}
```

`--json-report` / `--html-report` additionally save timestamped copies to `reports/` (useful for archiving multiple runs).

### `validate` — Rich table

Old output:
```
Valid — lab=my-test-lab provider=aws
  Instance:  t2.micro in us-east-1
  Storage:   10 GB
```

New output (Phase 6):
```
┌──────────────────────────────────────────┐
│          Spec Validation — OK ✓          │
├────────────────────┬─────────────────────┤
│ Field              │ Value               │
├────────────────────┼─────────────────────┤
│ Name               │ my-test-lab         │
│ Provider           │ aws                 │
│ Region             │ us-east-1           │
│ Instance Type      │ t2.micro            │
│ Storage            │ 10 GB               │
│ Tests              │ connectivity, api   │
│ Teardown on Success│ True                │
│ Teardown on Failure│ False               │
│ Tags               │ project=cloudforge  │
└────────────────────┴─────────────────────┘
✓ Spec is valid  examples/lab.yaml
```

---

## 15. Complete Data Flow — Phase 6 Final State

```
cloudforge run --spec examples/lab.yaml
  │
  ├─ load_spec("examples/lab.yaml")                    ← schema.py
  │    └─ yaml.safe_load() → LabSpec.model_validate()
  │
  ├─ get_provisioner(spec.provider, spec)              ← provisioner.py
  │    └─ Returns AWSProvisioner(spec)
  │
  ├─ _run_provision(provisioner, spec)                 ← cli.py helper
  │    └─ AWSProvisioner.provision()
  │         ├─ _launch_ec2()          → boto3: run_instances
  │         ├─ _wait_for_running()    → boto3: get_waiter("instance_running")
  │         ├─ _fetch_public_ip()     → boto3: describe_instances
  │         ├─ _create_s3_bucket()    → boto3: create_bucket
  │         ├─ tag_resources()        → boto3: create_tags + put_bucket_tagging
  │         └─ _write_state_file()   → .cloudforge_state.json
  │    → ProvisionResult(success=True, outputs={instance_id, public_ip, ...})
  │
  ├─ _print_provision_table(result.outputs)            ← cli.py helper → Rich table
  │
  ├─ run_suites(spec, outputs)                         ← runner.py
  │    ├─ _build_env(outputs) → os.environ + CLOUDFORGE_* vars
  │    └─ for each test_name in spec.tests:
  │         ├─ _resolve_path(name) → "tests/smoke/test_api.py"
  │         ├─ subprocess: python -m pytest tests/smoke/test_api.py -v
  │         └─ _parse_pytest_output() → SuiteResult(passed=2, ...)
  │    → RunResult(suites=[...])
  │
  ├─ run_teardown(spec)                                ← teardown.py
  │    ├─ _read_state() → load .cloudforge_state.json
  │    ├─ _aws_terminate_instance() → boto3 terminate + waiter
  │    ├─ _aws_delete_bucket()      → boto3 paginate + delete_objects + delete_bucket
  │    └─ _STATE_FILE.unlink()      → remove .cloudforge_state.json
  │    → TeardownResult(success=True, ...)
  │
  ├─ build_report(...)                                 ← reporter.py
  │    → dict with provision + tests + teardown sections
  │
  ├─ print_summary(report)                             ← reporter.py Rich table
  ├─ cloudforge_report.json.write_text(...)            ← always written
  ├─ save_json(report, "reports/")                     ← only if --json-report
  └─ save_html(report, "reports/")                     ← only if --html-report
```

---

## 16. Git History — All Six Phases

| Commit | Tag | What was built |
|---|---|---|
| `97ada3d` | Phase 1 | Full project scaffold: CLI, provisioner, runner, reporter, teardown, Terraform stubs, smoke tests, pyproject.toml |
| `152cc74` | Phase 2 | Flat Pydantic v2 `LabSpec`; `load_spec()`; `CloudProvider` enum; `@field_validator`; updated all consumers |
| `93d4fab` | Phase 3 | Direct boto3 `AWSProvisioner`: `run_instances`, `get_waiter`, `create_bucket`; `_run_provision()` wrapper in CLI |
| `06df9df` | Phase 4 | Production `terraform/aws/main.tf` + `terraform/gcp/main.tf`; `terraform/variables.tf`; `locals`, `merge()`, `random_id`, `keepers` |
| `f07c583` | Phase 5 | `tests/smoke/conftest.py` fixture chain; rewritten `test_connectivity.py` + `test_api.py`; new `test_performance.py`; `_write_state_file()` in provisioner |
| `f33f625` | Phase 6 | `--spec` flags everywhere; `--dry-run`; Rich tables; boto3 `teardown.py`; `cloudforge_report.json` |

---

## 17. Dependencies — What to Install

```toml
# pyproject.toml [project.dependencies]
click>=8.1
pydantic>=2.7
boto3>=1.34
pyyaml>=6.0
rich>=13.7
jinja2>=3.1
pytest>=8.2

# [project.optional-dependencies] dev
pytest-cov
ruff
mypy
boto3-stubs[ec2,s3,iam]
```

Install in a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 18. Key Design Decisions — Phases 3–6

### Why no `moto` in Phase 3?

`moto` is the AWS mocking library for unit tests. Phase 3 focused on getting real AWS calls working — mocking would have hidden API shape mistakes. Moto tests are a natural Phase 7 addition once the real-world behavior is validated.

### Why separate `_write_state_file()` in Phase 5 instead of env vars?

The conftest.py fixtures need resource IDs **before pytest starts** (session fixtures run at collection time). Environment variables set by the parent process are fine, but they require the parent to know the IDs — which means the runner would need to inject them. A file is simpler: the provisioner writes it, the fixtures read it, no coordination needed.

### Why `scope="session"` for all conftest fixtures?

If `scope="function"` (default), each test would re-read and re-validate the JSON file. With 7 tests across 3 files, that's 7 file reads. Session scope reads once and shares the dict. More importantly: a `pytest.skip()` in a function-scoped fixture only skips that one test; in a session fixture it propagates to all dependents, which is the correct behavior when the entire lab doesn't exist.

### Why keep `run_suites()` as subprocess instead of `pytest.main()`?

`pytest.main()` runs in the same process. A test that calls `sys.exit()` or has an uncaught exception can crash CloudForge. Subprocess isolation means:
1. A crashing test doesn't crash the provisioner
2. stdout/stderr are captured cleanly for `_parse_pytest_output()`
3. Environment variables (`CLOUDFORGE_*`) can be injected into just the test process

### Why always write `cloudforge_report.json` in Phase 6?

Before Phase 6, the report was only written if you passed `--json-report`. This meant silent runs produced no artifact — hard to audit or debug. A fixed-name file in the working directory is always there after `cloudforge run`, making it easy to `cat cloudforge_report.json` or `jq '.overall_success'` in a CI pipeline without any flags.

### Why rename `destroy` to `teardown`?

`destroy` is Terraform's terminology. Since Phase 6 tears down via boto3 (not Terraform), `teardown` is the more accurate and provider-agnostic name. It also matches the `teardown_on_success` / `teardown_on_failure` field names in the spec.

---

*Last updated: Phase 6 — May 2026*  
*Repository: https://github.com/shashank8walke/cloudforge*
