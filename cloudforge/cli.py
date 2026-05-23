"""CloudForge CLI — provision → test → teardown from a single YAML spec."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

from cloudforge.provisioner import ProvisionResult, get_provisioner
from cloudforge.reporter import build_report, print_summary, save_html, save_json
from cloudforge.runner import run_suites
from cloudforge.schema import load_spec
from cloudforge.teardown import run_teardown

console = Console()

# Path to the runtime state file written by the provisioner
_STATE_FILE = Path(".cloudforge_state.json")

# Default path for the JSON report produced by `cloudforge run`
_DEFAULT_REPORT = Path("cloudforge_report.json")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run_provision(provisioner, spec) -> ProvisionResult:
    """Call provisioner.provision() and normalise the result into a ProvisionResult."""
    start = time.monotonic()
    try:
        outputs = provisioner.provision()
        return ProvisionResult(
            success=True,
            provider=spec.provider.value,
            lab_name=spec.name,
            outputs=outputs,
            elapsed_seconds=time.monotonic() - start,
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        return ProvisionResult(
            success=False,
            provider=spec.provider.value,
            lab_name=spec.name,
            error=f"{code}: {msg}",
            elapsed_seconds=time.monotonic() - start,
        )
    except NotImplementedError as exc:
        return ProvisionResult(
            success=False,
            provider=spec.provider.value,
            lab_name=spec.name,
            error=str(exc),
            elapsed_seconds=time.monotonic() - start,
        )


def _load_state_file() -> dict | None:
    """Load .cloudforge_state.json; return None if missing or malformed."""
    if not _STATE_FILE.exists():
        return None
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_provision_table(outputs: dict) -> None:
    """Render a Rich table summarising every provisioned resource."""
    label_map = {
        "instance_id": "EC2 Instance ID",
        "public_ip": "Public IP",
        "s3_bucket": "S3 Bucket",
        "region": "Region",
        "launch_time": "Launch Time (s)",
    }
    table = Table(title="Provisioned Resources", show_lines=True)
    table.add_column("Resource", style="bold cyan")
    table.add_column("Value", style="green")
    for key, value in outputs.items():
        label = label_map.get(key, key.replace("_", " ").title())
        table.add_row(label, str(value))
    console.print(table)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

_BANNER = r"""
  ___  _                 _ _____
 / __\| | ___  _   _  __| |  ___|__  _ __ __ _  ___
/ /   | |/ _ \| | | |/ _` | |_ / _ \| '__/ _` |/ _ \
/ /___| | (_) | |_| | (_| |  _| (_) | | | (_| |  __/
\____/|_|\___/ \__,_|\__,_|_|  \___/|_|  \__, |\___|
                                          |___/
  Multi-Cloud Test Lab Provisioner  v0.1.0
"""


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("0.1.0", prog_name="cloudforge")
def cli() -> None:
    """CloudForge — provision cloud test labs, run smoke tests, tear down automatically."""
    console.print(f"[bold blue]{_BANNER}[/]")


# ---------------------------------------------------------------------------
# cloudforge provision --spec lab.yaml [--dry-run]
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--spec", "spec_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the lab YAML spec.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be created without touching AWS.",
)
def provision(spec_file: str, dry_run: bool) -> None:
    """Provision a lab environment from SPEC without running tests."""
    spec = load_spec(spec_file)

    if dry_run:
        console.print("\n[bold yellow]  Dry Run — nothing will be provisioned[/]\n")
        table = Table(title="Planned Resources (Dry Run)", show_lines=True)
        table.add_column("Resource", style="bold cyan")
        table.add_column("Planned Value", style="yellow")
        merged_tags = {**spec.tags, "ManagedBy": "cloudforge", "Lab": spec.name}
        table.add_row("Provider", spec.provider.value)
        table.add_row("Region", spec.region)
        table.add_row("EC2 Instance Type", spec.instance_type)
        table.add_row("Root Volume", f"{spec.storage_gb} GB")
        table.add_row("S3 Bucket Name", f"cloudforge-{spec.name}-<random8hex>")
        table.add_row("EC2 Tags", ", ".join(f"{k}={v}" for k, v in merged_tags.items()))
        table.add_row("State File", str(_STATE_FILE))
        console.print(table)
        return

    console.print(f"[bold]Provisioning:[/] {spec.name} on {spec.provider.value}")
    provisioner = get_provisioner(spec.provider, spec)
    result = _run_provision(provisioner, spec)

    if not result.success:
        console.print(f"[red]Provisioning failed:[/] {result.error}")
        sys.exit(1)

    _print_provision_table(result.outputs)
    console.print(
        f"\n[bold green]✓ Provisioning complete ({result.elapsed_seconds:.1f}s)[/]"
    )
    console.print(f"  Resource IDs saved to [bold]{_STATE_FILE}[/]")


# ---------------------------------------------------------------------------
# cloudforge test --spec lab.yaml
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--spec", "spec_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the lab YAML spec.",
)
def test(spec_file: str) -> None:
    """Run smoke tests against an already-provisioned lab.

    Reads .cloudforge_state.json to confirm a lab exists, then executes the
    test suites listed in the spec using pytest as a subprocess.  Results are
    displayed as a Rich table with per-suite pass/fail counts.
    """
    spec = load_spec(spec_file)

    state = _load_state_file()
    if state is None:
        console.print(
            f"[red]State file '{_STATE_FILE}' not found or invalid.[/]\n"
            f"  Run [bold]cloudforge provision --spec {spec_file}[/] first."
        )
        sys.exit(1)

    console.print(f"[bold]Testing:[/] {spec.name}")
    console.print(
        f"  Loaded state:  instance=[bold]{state.get('instance_id', 'N/A')}[/]"
        f"  bucket=[bold]{state.get('s3_bucket', 'N/A')}[/]"
    )

    result = run_suites(spec, state)

    # ── Rich results table ──────────────────────────────────────────────────
    table = Table(title="Test Results", show_lines=True)
    table.add_column("Suite", style="bold")
    table.add_column("Passed", style="green")
    table.add_column("Failed", style="red")
    table.add_column("Skipped", style="yellow")
    table.add_column("Duration")
    table.add_column("Status")

    for suite in result.suites:
        status_color = "green" if suite.success else "red"
        status_label = "PASS" if suite.success else "FAIL"
        table.add_row(
            Path(suite.suite_path).name,
            str(suite.passed),
            str(suite.failed + suite.errors),
            str(suite.skipped),
            f"{suite.duration_seconds:.1f}s",
            f"[{status_color}]{status_label}[/]",
        )

    console.print(table)

    overall_color = "green" if result.success else "red"
    overall_label = "ALL PASSED" if result.success else "FAILURES DETECTED"
    console.print(f"\n[bold {overall_color}]Tests: {overall_label}[/]")
    console.print(
        f"  passed={result.total_passed}  "
        f"failed={result.total_failed}  "
        f"({result.elapsed_seconds:.1f}s)"
    )

    sys.exit(0 if result.success else 1)


# ---------------------------------------------------------------------------
# cloudforge teardown --spec lab.yaml
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--spec", "spec_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the lab YAML spec.",
)
def teardown(spec_file: str) -> None:
    """Terminate EC2 instance, delete S3 bucket, and remove the state file.

    Reads .cloudforge_state.json for resource IDs.  On success the state file
    is deleted so subsequent commands know the lab no longer exists.
    """
    spec = load_spec(spec_file)
    console.print(f"[bold]Teardown:[/] {spec.name} ({spec.provider.value})")
    result = run_teardown(spec)
    if not result.success:
        console.print(f"[red]Teardown failed:[/] {result.error}")
        sys.exit(1)
    console.print(
        f"[bold green]✓ Teardown complete ({result.elapsed_seconds:.1f}s)[/]"
    )


# ---------------------------------------------------------------------------
# cloudforge run --spec lab.yaml   (full lifecycle)
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--spec", "spec_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the lab YAML spec.",
)
@click.option(
    "--no-teardown",
    is_flag=True,
    default=False,
    help="Skip automatic teardown regardless of spec flags.",
)
@click.option(
    "--json-report",
    is_flag=True,
    default=False,
    help="Also save a timestamped JSON report to reports/.",
)
@click.option(
    "--html-report",
    is_flag=True,
    default=False,
    help="Also save a timestamped HTML report to reports/.",
)
def run(
    spec_file: str,
    no_teardown: bool,
    json_report: bool,
    html_report: bool,
) -> None:
    """Full lifecycle: provision → test → teardown (controlled by spec flags).

    Always writes a JSON report to cloudforge_report.json in the current
    directory.  Pass --json-report / --html-report to also save timestamped
    copies under reports/.
    """
    spec = load_spec(spec_file)
    console.print(
        f"[bold]Lab:[/] {spec.name}  [bold]Provider:[/] {spec.provider.value}"
    )

    # ── Provision ───────────────────────────────────────────────────────────
    provisioner = get_provisioner(spec.provider, spec)
    provision_result = _run_provision(provisioner, spec)

    if provision_result.success:
        _print_provision_table(provision_result.outputs)
    else:
        console.print(
            f"[red]Provisioning failed — skipping tests.[/]\n{provision_result.error}"
        )

    # ── Test ────────────────────────────────────────────────────────────────
    run_result = None
    if provision_result.success:
        run_result = run_suites(spec, provision_result.outputs)

    # ── Teardown (conditional) ───────────────────────────────────────────────
    teardown_result = None
    tests_ok = run_result is None or run_result.success
    overall_ok = provision_result.success and tests_ok
    should_teardown = not no_teardown and (
        (overall_ok and spec.teardown_on_success)
        or (not overall_ok and spec.teardown_on_failure)
    )
    if should_teardown:
        teardown_result = run_teardown(spec)

    # ── Report ──────────────────────────────────────────────────────────────
    report = build_report(
        spec.name,
        spec.provider.value,
        provision_result,
        run_result,
        teardown_result,
    )
    print_summary(report)

    # Always write cloudforge_report.json in the working directory
    _DEFAULT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print(f"\n  JSON report saved to [bold]{_DEFAULT_REPORT}[/]")

    # Optional timestamped copies in reports/
    reports_dir = Path("reports")
    if json_report:
        save_json(report, reports_dir)
    if html_report:
        save_html(report, reports_dir)

    sys.exit(0 if report["overall_success"] else 1)


# ---------------------------------------------------------------------------
# cloudforge validate --spec lab.yaml
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--spec", "spec_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the lab YAML spec.",
)
def validate(spec_file: str) -> None:
    """Validate a lab YAML spec without provisioning anything.

    Parses and validates every field in the spec against the Pydantic schema.
    Exits 0 on success, 1 on validation error — safe to use in CI pipelines.
    """
    try:
        spec = load_spec(spec_file)

        table = Table(title="Spec Validation — OK ✓", show_lines=True)
        table.add_column("Field", style="bold cyan")
        table.add_column("Value")
        table.add_row("Name", spec.name)
        table.add_row("Provider", spec.provider.value)
        table.add_row("Region", spec.region)
        table.add_row("Instance Type", spec.instance_type)
        table.add_row("Storage", f"{spec.storage_gb} GB")
        table.add_row("Tests", ", ".join(spec.tests))
        table.add_row("Teardown on Success", str(spec.teardown_on_success))
        table.add_row("Teardown on Failure", str(spec.teardown_on_failure))
        if spec.tags:
            table.add_row(
                "Tags",
                ", ".join(f"{k}={v}" for k, v in spec.tags.items()),
            )

        console.print(table)
        console.print(
            f"\n[bold green]✓ Spec is valid[/]  "
            f"[dim]{spec_file}[/]"
        )

    except Exception as exc:
        console.print(f"[red]Invalid spec:[/] {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
