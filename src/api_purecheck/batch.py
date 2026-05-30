from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from api_purecheck.config import AuditConfig
from api_purecheck.runner import RunOptions, dry_run_report, run_audit


def load_batch_configs(path: str | Path) -> list[AuditConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults: dict[str, Any] = {}
    items: Any = data
    if isinstance(data, dict):
        defaults = data.get("defaults", {})
        items = data.get("targets", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("batch file must be a JSON array or an object with targets")
    configs = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"batch target #{index + 1} must be an object")
        merged = {**defaults, **item}
        configs.append(
            AuditConfig(
                base_url=str(merged.get("base_url", "")),
                api_key=str(merged.get("api_key", "")),
                claimed_model=str(merged.get("claimed_model") or merged.get("model") or ""),
                level=str(merged.get("level", "quick")),
                output_format="json",
                timeout_seconds=float(merged.get("timeout_seconds", 60.0)),
                baseline_dir=str(merged.get("baseline_dir", "baselines")),
                api_type=str(merged.get("api_type", "openai-compatible")),
                probe_file=str(merged.get("probe_file", "")),
            )
        )
    if not configs:
        raise ValueError("batch file must contain at least one target")
    for config in configs:
        config.validate()
    return configs


def batch_dry_run(configs: list[AuditConfig]) -> dict[str, Any]:
    reports = [dry_run_report(config) for config in configs]
    return {
        "tool": "api-purecheck",
        "status": "dry_run",
        "captured_at": datetime.now(UTC).isoformat(),
        "target_count": len(configs),
        "estimated_total_requests": sum(int(report["estimated_request_count"]) for report in reports),
        "targets": reports,
    }


def run_batch(configs: list[AuditConfig]) -> dict[str, Any]:
    reports = [
        run_audit(config, RunOptions(timeout_seconds=config.timeout_seconds))
        for config in configs
    ]
    return {
        "tool": "api-purecheck",
        "status": "completed",
        "captured_at": datetime.now(UTC).isoformat(),
        "target_count": len(configs),
        "summary": summarize_reports(reports),
        "attention_targets": attention_targets(reports),
        "reports": reports,
    }


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    consistency_counts: dict[str, int] = {}
    for report in reports:
        _increment(status_counts, str(report.get("status", "unknown")))
        _increment(risk_counts, str(report.get("risk_level", "unknown")))
        _increment(consistency_counts, str(report.get("claim_consistency", "unknown")))
    return {
        "status_counts": status_counts,
        "risk_counts": risk_counts,
        "claim_consistency_counts": consistency_counts,
    }


def attention_targets(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = []
    for index, report in enumerate(reports):
        config = report.get("config", {})
        if not isinstance(config, dict):
            config = {}
        checks = report.get("checks", {})
        if not isinstance(checks, dict):
            checks = {}
        anomaly_checks = [
            name
            for name, item in checks.items()
            if isinstance(item, dict) and item.get("status") == "anomaly"
        ]
        should_include = (
            report.get("status") != "completed"
            or report.get("risk_level") in {"medium", "high"}
            or report.get("claim_consistency") in {"low", "unavailable"}
            or bool(anomaly_checks)
        )
        if should_include:
            targets.append(
                {
                    "index": index + 1,
                    "base_url": config.get("base_url", ""),
                    "claimed_model": config.get("claimed_model", ""),
                    "status": report.get("status", "unknown"),
                    "claim_consistency": report.get("claim_consistency", "unknown"),
                    "risk_level": report.get("risk_level", "unknown"),
                    "anomaly_checks": anomaly_checks,
                }
            )
    return sorted(targets, key=_attention_sort_key)


def _attention_sort_key(item: dict[str, Any]) -> tuple[int, int]:
    risk_rank = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_rank = 0 if item.get("status") != "completed" else 1
    return (risk_rank.get(str(item.get("risk_level")), 2), status_rank)


def _increment(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1
