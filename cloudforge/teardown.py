"""Resource cleanup — runs lifecycle hooks then destroys Terraform state."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from cloudforge.schema import CloudProvider, LabSpec

console = Console()

TERRAFORM_AWS_DIR = Path(__file__).parent.parent / "terraform" / "aws"
TERRAFORM_GCP_DIR = Path(__file__).parent.parent / "terraform" / "gcp"

_TF_DIRS: dict[CloudProvider, Path] = {
    CloudProvider.aws: TERRAFORM_AWS_DIR,
    CloudProvider.gcp: TERRAFORM_GCP_DIR,
}


@dataclass
class TeardownResult:
    success: bool
    lab_name: str
    provider: str
    elapsed_seconds: float = 0.0
    error: str | None = None


def _run_hook(cmd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Hook timed out: {cmd}"
    except Exception as exc:
        return False, str(exc)


def _terraform_destroy(tf_dir: Path, var_file: Path | None = None) -> tuple[bool, str]:
    cmd = ["terraform", "destroy", "-auto-approve", "-no-color"]
    if var_file and var_file.exists():
        cmd += [f"-var-file={var_file}"]
    try:
        result = subprocess.run(cmd, cwd=tf_dir, capture_output=True, text=True, timeout=600)
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "terraform binary not found"
    except subprocess.TimeoutExpired:
        return False, "terraform destroy timed out after 600s"


def run_teardown(spec: LabSpec) -> TeardownResult:
    start = time.monotonic()
    console.print(f"\n[bold yellow]  Teardown:[/] {spec.name} ({spec.provider.value})")

    # Run on_teardown lifecycle hooks first
    for hook in spec.lifecycle.on_teardown:
        console.print(f"  Running hook: [dim]{hook}[/]")
        ok, out = _run_hook(hook)
        if not ok:
            console.print(f"  [yellow]Hook warning:[/] {out[:200]}")

    tf_dir = _TF_DIRS.get(spec.provider)
    if tf_dir is None:
        return TeardownResult(
            success=False,
            lab_name=spec.name,
            provider=spec.provider.value,
            error=f"No Terraform directory for provider {spec.provider.value}",
            elapsed_seconds=time.monotonic() - start,
        )

    var_file = tf_dir / f"{spec.name}.auto.tfvars.json"
    console.print("  Running [green]terraform destroy[/]…")
    ok, out = _terraform_destroy(tf_dir, var_file)

    # Clean up the var file regardless of destroy outcome
    if var_file.exists():
        var_file.unlink()

    elapsed = time.monotonic() - start
    if ok:
        console.print(f"[bold green]  Teardown complete in {elapsed:.1f}s[/]")
        return TeardownResult(True, spec.name, spec.provider.value, elapsed_seconds=elapsed)
    else:
        console.print(f"[bold red]  Teardown failed:[/] {out[:300]}")
        return TeardownResult(False, spec.name, spec.provider.value, elapsed_seconds=elapsed, error=out)
