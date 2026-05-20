"""CloudForge CLI — provision → test → teardown from a single YAML spec."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click
from botocore.exceptions import ClientError
from rich.console import Console

from cloudforge.provisioner import ProvisionResult, get_provisioner
from cloudforge.reporter import build_report, print_summary, save_html, save_json
from cloudforge.runner import run_suites
from cloudforge.schema import load_spec
from cloudforge.teardown import run_teardown

console = Console()

def _run_provision(provisioner, spec) -> ProvisionResult:
    """Call provisioner.provision() and normalise the result into ProvisionResult."""
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


_BANNER = r"""
  ___  _                 _ _____
 / __\| | ___  _   _  __| |  ___|__  _ __ __ _  ___
/ /   | |/ _ \| | | |/ _` | |_ / _ \| '__/ _` |/ _ \
/ /___| | (_) | |_| | (_| |  _| (_) | | | (_| |  __/
\____/|_|\___/ \__,_|\__,_|_|  \___/|_|  \__, |\___|
                                          |___/
  Multi-Cloud Test Lab Provisioner  v0.1.0
"""


@click.group()
@click.version_option("0.1.0", prog_name="cloudforge")
def cli() -> None:
    """CloudForge — provision cloud test labs, run smoke tests, tear down automatically."""
    console.print(f"[bold blue]{_BANNER}[/]")


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", "-o", default="reports", show_default=True, help="Directory for JSON/HTML reports")
@click.option("--no-teardown", is_flag=True, default=False, help="Skip automatic teardown (overrides spec)")
@click.option("--json-report", is_flag=True, default=False, help="Save JSON report")
@click.option("--html-report", is_flag=True, default=False, help="Save HTML report")
def run(spec_file: str, output_dir: str, no_teardown: bool, json_report: bool, html_report: bool) -> None:
    """Provision a lab, run tests, then tear down — full lifecycle from SPEC_FILE."""
    spec = load_spec(spec_file)
    console.print(f"[bold]Lab:[/] {spec.name}  [bold]Provider:[/] {spec.provider.value}")

    provisioner = get_provisioner(spec.provider, spec)
    provision_result = _run_provision(provisioner, spec)

    run_result = None
    if provision_result.success:
        run_result = run_suites(spec, provision_result.outputs)
    else:
        console.print(f"[red]Provisioning failed — skipping tests.[/]\n{provision_result.error}")

    teardown_result = None
    tests_ok = run_result is None or run_result.success
    overall_ok = provision_result.success and tests_ok
    should_teardown = not no_teardown and (
        (overall_ok and spec.teardown_on_success)
        or (not overall_ok and spec.teardown_on_failure)
    )

    if should_teardown:
        teardown_result = run_teardown(spec)

    report = build_report(spec.name, spec.provider.value, provision_result, run_result, teardown_result)
    print_summary(report)

    out = Path(output_dir)
    if json_report:
        save_json(report, out)
    if html_report:
        save_html(report, out)

    sys.exit(0 if report["overall_success"] else 1)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True, dir_okay=False))
def provision(spec_file: str) -> None:
    """Provision a lab environment without running tests."""
    spec = load_spec(spec_file)
    console.print(f"[bold]Provisioning:[/] {spec.name} on {spec.provider.value}")
    provisioner = get_provisioner(spec.provider, spec)
    result = _run_provision(provisioner, spec)
    if not result.success:
        console.print(f"[red]Failed:[/] {result.error}")
        sys.exit(1)
    console.print(f"[green]Done.[/] Outputs: {result.outputs}")


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True, dir_okay=False))
def test(spec_file: str) -> None:
    """Run test suites against an already-provisioned lab."""
    spec = load_spec(spec_file)
    console.print(f"[bold]Testing:[/] {spec.name}")
    result = run_suites(spec, {})
    sys.exit(0 if result.success else 1)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True, dir_okay=False))
def destroy(spec_file: str) -> None:
    """Tear down all resources for a lab."""
    spec = load_spec(spec_file)
    console.print(f"[bold]Destroying:[/] {spec.name}")
    result = run_teardown(spec)
    if not result.success:
        console.print(f"[red]Teardown failed:[/] {result.error}")
        sys.exit(1)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True, dir_okay=False))
def validate(spec_file: str) -> None:
    """Validate a lab YAML spec without provisioning anything."""
    try:
        spec = load_spec(spec_file)
        console.print(f"[green]Valid[/] — lab=[bold]{spec.name}[/] provider=[bold]{spec.provider.value}[/]")
        console.print(f"  Instance:       {spec.instance_type} in {spec.region}")
        console.print(f"  Storage:        {spec.storage_gb} GB")
        console.print(f"  Tests:          {', '.join(spec.tests)}")
        console.print(f"  Teardown:       on_success={spec.teardown_on_success}  on_failure={spec.teardown_on_failure}")
    except Exception as exc:
        console.print(f"[red]Invalid spec:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
