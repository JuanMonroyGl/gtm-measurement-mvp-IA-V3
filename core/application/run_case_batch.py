"""Batch runner for demo cases."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.application.run_case import run_case
from core.checks.check_case_output import check_case_outputs
from core.cli.context import parse_case_context


@dataclass(frozen=True)
class BatchRunOptions:
    prefix: str
    start: int
    end: int
    clean_outputs: bool
    strict_checks: bool
    stop_on_error: bool


def _case_ids(options: BatchRunOptions) -> list[str]:
    if options.start > options.end:
        raise ValueError("--from no puede ser mayor que --to")
    return [f"{options.prefix}{index}" for index in range(options.start, options.end + 1)]


def _clean_case_output(repo_root: Path, case_id: str) -> bool:
    outputs_root = (repo_root / "outputs").resolve()
    output_dir = (outputs_root / case_id).resolve()
    if output_dir.parent != outputs_root:
        raise ValueError(f"Ruta de output fuera de outputs/: {output_dir}")
    if not output_dir.exists():
        return False
    shutil.rmtree(output_dir)
    return True


def run_case_batch(repo_root: Path, options: BatchRunOptions) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    started_at = time.time()
    results: list[dict[str, Any]] = []

    for case_id in _case_ids(options):
        case_started_at = time.time()
        result: dict[str, Any] = {
            "case_id": case_id,
            "input_dir": str((repo_root / "inputs" / case_id).resolve()),
            "output_dir": str((repo_root / "outputs" / case_id).resolve()),
            "output_cleaned": False,
            "strict_check_passed": None,
            "status": "pending",
            "error": None,
        }
        try:
            if options.clean_outputs:
                result["output_cleaned"] = _clean_case_output(repo_root, case_id)

            context = parse_case_context(repo_root=repo_root, case_path=Path("inputs") / case_id)
            run_result = run_case(context)
            result.update(
                {
                    "status": run_result.get("status") or "success",
                    "warnings_count": run_result.get("warnings_count"),
                    "run_summary": run_result.get("run_summary"),
                    "tag_template": run_result.get("tag_template"),
                    "trigger_selector": run_result.get("trigger_selector"),
                    "report": run_result.get("report"),
                }
            )
            if options.strict_checks:
                check_case_outputs(repo_root=repo_root, case_id=case_id)
                result["strict_check_passed"] = True
        except Exception as exc:  # noqa: BLE001 - batch must record per-case failures.
            result["status"] = "error"
            result["error"] = str(exc)
            if options.strict_checks and result["strict_check_passed"] is None:
                result["strict_check_passed"] = False
            if options.stop_on_error:
                result["duration_seconds"] = round(time.time() - case_started_at, 2)
                results.append(result)
                break

        result["duration_seconds"] = round(time.time() - case_started_at, 2)
        results.append(result)

    failed = [item for item in results if item.get("status") == "error"]
    summary = {
        "case_ids": _case_ids(options),
        "total_cases": len(results),
        "passed_cases": len(results) - len(failed),
        "failed_cases": len(failed),
        "clean_outputs": options.clean_outputs,
        "strict_checks": options.strict_checks,
        "stop_on_error": options.stop_on_error,
        "duration_seconds": round(time.time() - started_at, 2),
        "results": results,
    }
    summary_path = repo_root / "outputs" / f"batch_{options.prefix}{options.start}_{options.prefix}{options.end}_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
