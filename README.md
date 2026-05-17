# CloudForge — Multi-Cloud Test Lab Provisioner

> **Provision → Test → Teardown** — automated cloud test lab lifecycle from a single YAML spec.

QA and DevOps teams waste hours manually spinning up cloud environments, running tests, and forgetting to clean up — leaving orphaned resources and surprise bills. CloudForge automates the full lifecycle in one command.

```
cloudforge run examples/lab.yaml --html-report
```

---

## Features

| Feature | Status |
|---|---|
| AWS provisioning via Terraform + boto3 | Phase 1 |
| Pytest smoke suite runner | Phase 1 |
| Auto-teardown via lifecycle hooks | Phase 1 |
| JSON + HTML report generation | Phase 1 |
| Pydantic v2 YAML schema validation | Phase 1 |
| GCP provisioning | Phase 2 |
| Azure provisioning | Phase 2 |
| Parallel multi-cloud labs | Phase 3 |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Terraform >= 1.6
- AWS CLI configured (`aws configure`)

### Install

```bash
pip install -e ".[dev]"
```

### Validate a spec

```bash
cloudforge validate examples/lab.yaml
```

### Full lifecycle (provision → test → teardown)

```bash
cloudforge run examples/lab.yaml --html-report --json-report
```

### Individual commands

```bash
# Provision only
cloudforge provision examples/lab.yaml

# Run tests against an already-provisioned lab
cloudforge test examples/lab.yaml

# Tear down resources
cloudforge destroy examples/lab.yaml
```

---

## Lab Spec (YAML)

```yaml
name: my-api-lab
provider: aws           # aws | gcp | azure

instance:
  type: t3.micro
  count: 2
  region: us-east-1

network:
  vpc_cidr: "10.0.0.0/16"
  public_subnets: ["10.0.1.0/24"]

tests:
  - path: tests/smoke/test_connectivity.py
    markers: [smoke]
    timeout_seconds: 120
    env_vars:
      MY_VAR: value

lifecycle:
  on_provision: ["echo 'ready'"]
  on_teardown:  ["echo 'cleanup'"]
  auto_teardown: true
  teardown_on_failure: false
```

Full schema reference: [cloudforge/schema.py](cloudforge/schema.py)

---

## Project Structure

```
cloudforge/
  cli.py          # Click CLI entrypoint (run, provision, test, destroy, validate)
  provisioner.py  # Cloud provisioner — AWS (boto3 + Terraform), GCP/Azure stubs
  runner.py       # Pytest test runner with env-var injection
  teardown.py     # Resource cleanup with lifecycle hook support
  reporter.py     # JSON + HTML report generator
  schema.py       # Pydantic v2 YAML schema validator
tests/
  smoke/
    test_connectivity.py   # Network / SSH / HTTP connectivity checks
    test_api.py            # API health, JSON, latency + EC2 IMDSv2 checks
terraform/
  aws/main.tf    # VPC, subnets, SG, EC2 instances
  gcp/main.tf    # Stub — Phase 2
examples/
  lab.yaml       # Example lab spec
```

---

## Environment Variables Injected by Runner

Terraform outputs are automatically injected as `CLOUDFORGE_<KEY>` environment variables so your tests can discover endpoints without hardcoding:

| Variable | Source |
|---|---|
| `CLOUDFORGE_PUBLIC_IP` | First EC2 public IP |
| `CLOUDFORGE_VPC_ID` | VPC ID |
| `CLOUDFORGE_REGION` | AWS region |
| `CLOUDFORGE_LAB_NAME` | Lab name from spec |
| `CLOUDFORGE_API_ENDPOINT` | Custom output (if defined) |

---

## Reports

After `cloudforge run --html-report --json-report`:

```
reports/
  report_<lab>_<timestamp>.json
  report_<lab>_<timestamp>.html
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check cloudforge/
```

---

## License

MIT — see [LICENSE](LICENSE).
