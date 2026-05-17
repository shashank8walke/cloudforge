"""Pytest test runner — executes smoke suites against provisioned labs."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from cloudforge.schema import LabSpec

console = Console()

# Maps the short test names used in lab specs to their actual file paths.
_TEST_PATH_MAP: dict[str, str] = {
    "connectivity": "tests/smoke/test_connectivity.py",
    "api": "tests/smoke/test_api.py",
    "performance": "tests/smoke/test_performance.py",
}

_DEFAULT_TIMEOUT = 300


@dataclass
class SuiteResult:
    suite_path: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped


@dataclass
class RunResult:
    lab_name: str
    suites: list[SuiteResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return all(s.success for s in self.suites)

    @property
    def total_passed(self) -> int:
        return sum(s.passed for s in self.suites)

    @property
    def total_failed(self) -> int:
        return sum(s.failed + s.errors for s in self.suites)


def _parse_pytest_output(stdout: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for line in stdout.splitlines():
        lower = line.lower()
        for key in counts:
            if key in lower:
                parts = lower.split()
                for i, part in enumerate(parts):
                    if part == key or part.startswith(key):
                        try:
                            counts[key] = int(parts[i - 1])
                        except (IndexError, ValueError):
                            pass
    return counts


def _resolve_path(test_name: str) -> str:
    """Return the file path for a test name, falling back to the name itself."""
    return _TEST_PATH_MAP.get(test_name.lower(), test_name)


def _build_env(outputs: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    for k, v in outputs.items():
        env[f"CLOUDFORGE_{k.upper()}"] = str(v)
    return env


def run_suites(spec: LabSpec, outputs: dict[str, Any]) -> RunResult:
    start = time.monotonic()
    result = RunResult(lab_name=spec.name)

    if not spec.tests:
        console.print("[yellow]  No tests defined in lab spec — skipping.[/]")
        return result

    env = _build_env(outputs)
    env["CLOUDFORGE_LAB_NAME"] = spec.name
    env["CLOUDFORGE_REGION"] = spec.region

    for test_name in spec.tests:
        path = _resolve_path(test_name)
        console.print(f"\n[bold cyan]  Running suite:[/] {test_name} ({path})")
        suite_start = time.monotonic()

        cmd = ["python", "-m", "pytest", path, "-v", "--tb=short", "--no-header",
               f"--timeout={_DEFAULT_TIMEOUT}"]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                                  timeout=_DEFAULT_TIMEOUT + 30)
            counts = _parse_pytest_output(proc.stdout)
            suite_result = SuiteResult(
                suite_path=path,
                passed=counts["passed"],
                failed=counts["failed"],
                errors=counts["errors"],
                skipped=counts["skipped"],
                duration_seconds=time.monotonic() - suite_start,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            suite_result = SuiteResult(
                suite_path=path,
                exit_code=1,
                duration_seconds=time.monotonic() - suite_start,
                stderr=f"Suite timed out after {_DEFAULT_TIMEOUT}s",
            )
        except FileNotFoundError:
            suite_result = SuiteResult(
                suite_path=path,
                exit_code=1,
                stderr="pytest / python not found in PATH",
            )

        _print_suite_summary(suite_result)
        result.suites.append(suite_result)

    result.elapsed_seconds = time.monotonic() - start
    return result


def _print_suite_summary(r: SuiteResult) -> None:
    color = "green" if r.success else "red"
    status = "PASSED" if r.success else "FAILED"
    console.print(
        f"  [{color}]{status}[/] — "
        f"passed={r.passed} failed={r.failed} errors={r.errors} skipped={r.skipped} "
        f"({r.duration_seconds:.1f}s)"
    )
