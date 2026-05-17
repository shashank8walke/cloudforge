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
