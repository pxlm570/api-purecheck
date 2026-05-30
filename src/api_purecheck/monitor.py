from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from time import sleep
from typing import Any

from api_purecheck.config import AuditConfig
from api_purecheck.runner import RunOptions, dry_run_report, run_audit


def monitor_dry_run(config: AuditConfig, *, runs: int, interval_seconds: float, output_dir: str) -> dict[str, Any]:
    if runs <= 0:
        raise ValueError("runs must be greater than 0")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be greater than or equal to 0")
    report = dry_run_report(config)
    report.update(
        {
            "monitor": {
                "runs": runs,
                "interval_seconds": interval_seconds,
                "output_dir": output_dir,
                "estimated_total_requests": report["estimated_request_count"] * runs,
            }
        }
    )
    return report


def run_monitor(
    config: AuditConfig,
    *,
    runs: int,
    interval_seconds: float,
    output_dir: str,
) -> dict[str, Any]:
    if runs <= 0:
        raise ValueError("runs must be greater than 0")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be greater than or equal to 0")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    written_files = []

    for index in range(runs):
        report = run_audit(config, RunOptions(timeout_seconds=config.timeout_seconds))
        report["monitor"] = {
            "run_index": index + 1,
            "runs": runs,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        filename = f"api-purecheck-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{index + 1}.json"
        target = output_path / filename
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written_files.append(str(target))
        if index < runs - 1:
            sleep(interval_seconds)

    return {
        "status": "completed",
        "runs": runs,
        "output_dir": str(output_path),
        "files": written_files,
        "config": config.redacted(),
    }
