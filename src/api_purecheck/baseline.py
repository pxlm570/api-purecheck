from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from api_purecheck.adapters.factory import make_client
from api_purecheck.adapters.openai_compatible import ApiRequestError
from api_purecheck.config import AuditConfig
from api_purecheck.probes import build_probes, evaluate_probe


@dataclass(frozen=True)
class BaselineOptions:
    provider: str
    output: str


@dataclass(frozen=True)
class BaselineModelStats:
    model: str
    providers: tuple[str, ...]
    rows: int
    probe_scores: dict[str, float]
    captured_at_min: str
    captured_at_max: str


def collect_baseline(config: AuditConfig, options: BaselineOptions) -> dict[str, Any]:
    client = make_client(config, config.timeout_seconds)
    captured_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []

    for probe in build_probes(config.level):
        started = perf_counter()
        row: dict[str, Any] = {
            "schema_version": 1,
            "captured_at": captured_at,
            "provider": options.provider,
            "claimed_model": config.claimed_model,
            "api_type": config.api_type,
            "level": config.level,
            "probe_id": probe.probe_id,
            "probe_title": probe.title,
        }
        try:
            completion = client.create_chat_completion(
                model=config.claimed_model,
                messages=probe.messages(),
                max_tokens=probe.max_tokens,
            )
            evaluation = evaluate_probe(probe, completion.content)
            row.update(
                {
                    "ok": True,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "self_reported_model": completion.model,
                    "finish_reason": completion.finish_reason,
                    "usage": completion.usage,
                    "score": evaluation.score,
                    "passed": evaluation.passed,
                    "response_text": completion.content,
                }
            )
        except ApiRequestError as exc:
            row.update(
                {
                    "ok": False,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "status_code": exc.status_code,
                    "error": str(exc),
                }
            )
        rows.append(row)

    output_path = Path(options.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "completed",
        "provider": options.provider,
        "claimed_model": config.claimed_model,
        "level": config.level,
        "output": str(output_path),
        "rows": len(rows),
        "success_rows": sum(1 for row in rows if row.get("ok")),
        "captured_at": captured_at,
        "config": config.redacted(),
    }


def load_baseline_stats(baseline_dir: str | Path) -> dict[str, BaselineModelStats]:
    root = Path(baseline_dir)
    if not root.exists():
        return {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in root.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = str(row.get("claimed_model") or row.get("model") or "").strip()
            if not model:
                continue
            grouped.setdefault(model, []).append(row)

    stats: dict[str, BaselineModelStats] = {}
    for model, rows in grouped.items():
        probe_values: dict[str, list[float]] = {}
        providers = set()
        captured_values = []
        for row in rows:
            provider = row.get("provider")
            if provider:
                providers.add(str(provider))
            probe_id = str(row.get("probe_id", "")).strip()
            if not probe_id:
                continue
            captured_at = row.get("captured_at")
            if captured_at:
                captured_values.append(str(captured_at))
            if row.get("ok") is False:
                continue
            try:
                score = float(row.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            probe_values.setdefault(probe_id, []).append(score)
        stats[model] = BaselineModelStats(
            model=model,
            providers=tuple(sorted(providers)),
            rows=len(rows),
            probe_scores={
                probe_id: sum(values) / len(values)
                for probe_id, values in probe_values.items()
                if values
            },
            captured_at_min=min(captured_values) if captured_values else "",
            captured_at_max=max(captured_values) if captured_values else "",
        )
    return stats
