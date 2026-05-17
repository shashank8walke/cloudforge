"""Report generator — produces JSON and HTML summaries of a CloudForge run."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from cloudforge.provisioner import ProvisionResult
from cloudforge.runner import RunResult
from cloudforge.teardown import TeardownResult

console = Console()

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CloudForge Report — {lab_name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; color: #1a1a2e; }}
    h1 {{ color: #16213e; }} h2 {{ color: #0f3460; border-bottom: 2px solid #e94560; padding-bottom: 4px; }}
    .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: .85em; font-weight: 600; }}
    .pass {{ background: #d4edda; color: #155724; }} .fail {{ background: #f8d7da; color: #721c24; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th {{ background: #16213e; color: #fff; padding: 8px 12px; text-align: left; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #dee2e6; }}
    tr:hover {{ background: #f8f9fa; }}
    pre {{ background: #f1f3f5; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: .82em; }}
    .meta {{ color: #6c757d; font-size: .9em; }}
  </style>
</head>
<body>
  <h1>CloudForge Lab Report</h1>
  <p class="meta">Lab: <strong>{lab_name}</strong> &nbsp;|&nbsp; Provider: <strong>{provider}</strong> &nbsp;|&nbsp; Generated: {generated_at}</p>
  <span class="badge {overall_cls}">{overall_status}</span>

  <h2>Provision</h2>
  <table><tr><th>Key</th><th>Value</th></tr>{provision_rows}</table>

  <h2>Test Suites</h2>
  <table>
    <tr><th>Suite</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Duration</th><th>Status</th></tr>
    {suite_rows}
  </table>

  <h2>Teardown</h2>
  <table><tr><th>Key</th><th>Value</th></tr>{teardown_rows}</table>

  <h2>Raw JSON</h2>
  <pre>{raw_json}</pre>
</body>
</html>
"""


def _kv_rows(d: dict[str, Any]) -> str:
    return "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in d.items())


def build_report(
    spec_name: str,
    provider: str,
    provision: ProvisionResult,
    run: RunResult | None,
    teardown: TeardownResult | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    overall_ok = provision.success and (run is None or run.success) and (teardown is None or teardown.success)

    report: dict[str, Any] = {
        "lab_name": spec_name,
        "provider": provider,
        "generated_at": now,
        "overall_success": overall_ok,
        "provision": {
            "success": provision.success,
            "elapsed_seconds": round(provision.elapsed_seconds, 2),
            "outputs": provision.outputs,
            "error": provision.error,
        },
        "tests": None,
        "teardown": None,
    }

    if run is not None:
        report["tests"] = {
            "success": run.success,
            "elapsed_seconds": round(run.elapsed_seconds, 2),
            "total_passed": run.total_passed,
            "total_failed": run.total_failed,
            "suites": [
                {
                    "path": s.suite_path,
                    "passed": s.passed,
                    "failed": s.failed,
                    "errors": s.errors,
                    "skipped": s.skipped,
                    "duration_seconds": round(s.duration_seconds, 2),
                    "exit_code": s.exit_code,
                }
                for s in run.suites
            ],
        }

    if teardown is not None:
        report["teardown"] = {
            "success": teardown.success,
            "elapsed_seconds": round(teardown.elapsed_seconds, 2),
            "error": teardown.error,
        }

    return report


def save_json(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"report_{report['lab_name']}_{ts}.json"
    path.write_text(json.dumps(report, indent=2))
    console.print(f"  JSON report: [link]{path}[/]")
    return path


def save_html(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"report_{report['lab_name']}_{ts}.html"

    prov = report["provision"]
    provision_rows = _kv_rows(
        {
            "Success": prov["success"],
            "Elapsed": f"{prov['elapsed_seconds']}s",
            "Error": prov["error"] or "—",
            **{f"Output: {k}": v for k, v in (prov.get("outputs") or {}).items()},
        }
    )

    suite_rows = ""
    if report["tests"]:
        for s in report["tests"]["suites"]:
            cls = "pass" if s["exit_code"] == 0 else "fail"
            status = "PASS" if s["exit_code"] == 0 else "FAIL"
            suite_rows += (
                f"<tr><td>{s['path']}</td><td>{s['passed']}</td><td>{s['failed']}</td>"
                f"<td>{s['skipped']}</td><td>{s['duration_seconds']}s</td>"
                f"<td><span class='badge {cls}'>{status}</span></td></tr>"
            )
    else:
        suite_rows = "<tr><td colspan='6'>No test suites ran</td></tr>"

    td = report.get("teardown") or {}
    teardown_rows = _kv_rows(
        {"Success": td.get("success", "N/A"), "Elapsed": f"{td.get('elapsed_seconds', 0)}s", "Error": td.get("error") or "—"}
    )

    overall_ok = report["overall_success"]
    html = _HTML_TEMPLATE.format(
        lab_name=report["lab_name"],
        provider=report["provider"],
        generated_at=report["generated_at"],
        overall_cls="pass" if overall_ok else "fail",
        overall_status="ALL PASSED" if overall_ok else "FAILURES DETECTED",
        provision_rows=provision_rows,
        suite_rows=suite_rows,
        teardown_rows=teardown_rows,
        raw_json=json.dumps(report, indent=2),
    )
    path.write_text(html)
    console.print(f"  HTML report: [link]{path}[/]")
    return path


def print_summary(report: dict[str, Any]) -> None:
    overall = report["overall_success"]
    color = "green" if overall else "red"
    label = "ALL PASSED" if overall else "FAILURES DETECTED"

    table = Table(title=f"CloudForge — {report['lab_name']}", show_lines=True)
    table.add_column("Phase", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    prov = report["provision"]
    table.add_row(
        "Provision",
        f"[{'green' if prov['success'] else 'red'}]{'OK' if prov['success'] else 'FAIL'}[/]",
        f"{prov['elapsed_seconds']}s",
    )

    if report["tests"]:
        t = report["tests"]
        table.add_row(
            "Tests",
            f"[{'green' if t['success'] else 'red'}]{'OK' if t['success'] else 'FAIL'}[/]",
            f"passed={t['total_passed']} failed={t['total_failed']} ({t['elapsed_seconds']}s)",
        )

    if report.get("teardown"):
        td = report["teardown"]
        table.add_row(
            "Teardown",
            f"[{'green' if td['success'] else 'red'}]{'OK' if td['success'] else 'FAIL'}[/]",
            f"{td['elapsed_seconds']}s",
        )

    console.print(table)
    console.print(f"\n[bold {color}]Overall: {label}[/]\n")
