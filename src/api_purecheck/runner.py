from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from time import perf_counter
from typing import Any

from api_purecheck import __version__
from api_purecheck.adapters.factory import make_client
from api_purecheck.adapters.openai_compatible import ApiRequestError
from api_purecheck.baseline import BaselineModelStats, load_baseline_stats
from api_purecheck.config import AuditConfig, base_url_warnings, normalize_base_url
from api_purecheck.model_profiles import match_model_profile, profile_match_to_dict
from api_purecheck.probes import Probe, build_probes, evaluate_probe, load_probes_from_file


@dataclass(frozen=True)
class RunOptions:
    timeout_seconds: float = 60.0


HARD_FAILURE_STATUS_CODES = {400, 401, 403, 404, 405}
CHECK_CLEAN = "clean"
CHECK_ANOMALY = "anomaly"
CHECK_INCONCLUSIVE = "inconclusive"


def estimate_request_count(level: str) -> int:
    return len(build_probes(level)) + _service_check_request_count(level)


def probes_for_config(config: AuditConfig) -> list[Probe]:
    if config.probe_file:
        return load_probes_from_file(config.probe_file)
    return build_probes(config.level)


def _service_check_request_count(level: str) -> int:
    return 2 if level in {"standard", "deep"} else 0


def _should_run_service_checks(config: AuditConfig, probe_results: list[dict[str, Any]]) -> bool:
    if config.level not in {"standard", "deep"}:
        return False
    return any(result.get("ok") for result in probe_results)


def _run_stream_check(config: AuditConfig, client: Any) -> dict[str, Any]:
    started = perf_counter()
    try:
        result = client.create_stream_check(model=config.claimed_model)
        latency_ms = round((perf_counter() - started) * 1000, 2)
        content = result.content[:300]
        passed = bool(result.ok and "PURECHECK_STREAM_OK" in result.content and (result.done_seen or result.finish_seen))
        return {
            "ok": True,
            "passed": passed,
            "latency_ms": latency_ms,
            "event_count": result.event_count,
            "done_seen": result.done_seen,
            "finish_seen": result.finish_seen,
            "content_type": result.content_type,
            "raw_event_types": result.raw_event_types,
            "event_type_counts": result.event_type_counts,
            "sample": content,
            "reason": "流式响应包含有效事件、目标内容和结束信号。" if passed else "流式响应缺少目标内容或结束信号。",
        }
    except ApiRequestError as exc:
        latency_ms = round((perf_counter() - started) * 1000, 2)
        raw_error = str(exc)
        return {
            "ok": False,
            "passed": False,
            "latency_ms": latency_ms,
            "error": _redact_sensitive(raw_error, config.api_key),
            "status_code": exc.status_code,
            "sensitive_leak_detected": _contains_sensitive(raw_error, config.api_key),
            "reason": "stream 请求失败，无法完成流式完整性检查。",
        }


def _run_error_leakage_probe(config: AuditConfig, client: Any) -> dict[str, Any]:
    started = perf_counter()
    invalid_model = "api-purecheck-invalid-model"
    probe = Probe(
        probe_id="risk.error.invalid_model",
        title="错误泄漏专门检查",
        prompt="请只输出 OK。",
        validator="contains",
        expected="OK",
        max_tokens=8,
    )
    try:
        completion = client.create_chat_completion(
            model=invalid_model,
            messages=probe.messages(),
            max_tokens=probe.max_tokens,
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {
            "ok": True,
            "passed": False,
            "latency_ms": latency_ms,
            "model": completion.model,
            "sample": completion.content[:120],
            "reason": "无效模型名请求被服务端接受，未产生可检查的错误响应。",
        }
    except ApiRequestError as exc:
        latency_ms = round((perf_counter() - started) * 1000, 2)
        raw_error = str(exc)
        return {
            "ok": False,
            "passed": True,
            "latency_ms": latency_ms,
            "status_code": exc.status_code,
            "error": _redact_sensitive(raw_error, config.api_key),
            "sensitive_leak_detected": _contains_sensitive(raw_error, config.api_key),
            "reason": "已获取错误响应并完成敏感信息泄漏检查。",
        }


def run_audit(config: AuditConfig, options: RunOptions | None = None) -> dict[str, Any]:
    options = options or RunOptions()
    probes = probes_for_config(config)
    client = make_client(config, options.timeout_seconds)

    probe_results = []
    for probe in probes:
        started = perf_counter()
        try:
            completion = client.create_chat_completion(
                model=config.claimed_model,
                messages=probe.messages(),
                max_tokens=probe.max_tokens,
            )
            latency_ms = round((perf_counter() - started) * 1000, 2)
            evaluation = evaluate_probe(probe, completion.content)
            probe_results.append(
                {
                    "probe_id": probe.probe_id,
                    "title": probe.title,
                    "ok": True,
                    "latency_ms": latency_ms,
                    "self_reported_model": completion.model,
                    "finish_reason": completion.finish_reason,
                    "usage": completion.usage,
                    "raw_keys": completion.raw_keys,
                    "prompt_chars": _prompt_char_count(probe),
                    "score": evaluation.score,
                    "passed": evaluation.passed,
                    "reason": evaluation.reason,
                    "sample": completion.content[:300],
                }
            )
        except ApiRequestError as exc:
            latency_ms = round((perf_counter() - started) * 1000, 2)
            raw_error = str(exc)
            probe_results.append(
                _failed_probe(
                    probe,
                    _redact_sensitive(raw_error, config.api_key),
                    latency_ms,
                    exc.status_code,
                    _contains_sensitive(raw_error, config.api_key),
                )
            )
            if exc.status_code in HARD_FAILURE_STATUS_CODES or exc.status_code is None:
                break

    baselines = load_baseline_stats(config.baseline_dir)
    run_service_checks = _should_run_service_checks(config, probe_results)
    stream_result = _run_stream_check(config, client) if run_service_checks else None
    error_probe_result = _run_error_leakage_probe(config, client) if run_service_checks else None
    scores = _score_results(config.claimed_model, probe_results, baselines)
    checks = _risk_checks(config.claimed_model, probe_results, stream_result, error_probe_result)
    risk_level = _risk_level(checks)
    behavior_fingerprint = _behavior_fingerprint(probe_results)
    family_likelihoods = _family_likelihoods(config.api_type, scores["model_profile"], checks, behavior_fingerprint)
    diagnostics = _diagnostics(config, probe_results)
    status = _status_from_scores(scores, diagnostics)
    message = _message_for_status(status)
    return {
        "tool": "api-purecheck",
        "version": __version__,
        "status": status,
        "message": message,
        "config": config.redacted(),
        "request_count": len(probe_results) + (1 if stream_result else 0) + (1 if error_probe_result else 0),
        "planned_request_count": len(probes) + _service_check_request_count(config.level),
        "scores": scores["scores"],
        "claim_consistency": scores["claim_consistency"],
        "confidence": scores["confidence"],
        "risk_level": risk_level,
        "checks": checks,
        "behavior_fingerprint": behavior_fingerprint,
        "family_likelihoods": family_likelihoods,
        "top_matches": scores["top_matches"],
        "evidence": scores["evidence"],
        "diagnostics": diagnostics,
        "baseline": scores["baseline"],
        "model_profile": scores["model_profile"],
        "probe_results": probe_results,
        "stream_result": stream_result,
        "error_probe_result": error_probe_result,
        "limitations": [
            "本工具基于协议特征和黑盒行为做概率判断，不提供密码学证明。",
            "真实模型可能不在当前候选集内，因此报告保留“其他模型”概率空间。",
            "官方基线不是必需项；未加载基线时，结论基于轻量探针和协议诊断，应作为参考而非最终裁定。",
        ],
    }


def dry_run_report(config: AuditConfig) -> dict[str, Any]:
    return {
        "tool": "api-purecheck",
        "version": __version__,
        "status": "dry_run",
        "message": "配置校验通过。dry-run 不会发起真实 API 请求。",
        "config": config.redacted(),
        "effective_base_url": normalize_base_url(config.base_url, config.api_type),
        "estimated_request_count": len(probes_for_config(config)) + _service_check_request_count(config.level),
        "warnings": base_url_warnings(config.base_url, config.api_type),
        "limitations": [
            "dry-run 只校验配置和预计请求数，不会判断模型一致性。",
        ],
    }


def _failed_probe(
    probe: Probe,
    error_message: str,
    latency_ms: float,
    status_code: int | None,
    sensitive_leak_detected: bool = False,
) -> dict[str, Any]:
    return {
        "probe_id": probe.probe_id,
        "title": probe.title,
        "ok": False,
        "latency_ms": latency_ms,
        "status_code": status_code,
        "error": error_message,
        "sensitive_leak_detected": sensitive_leak_detected,
        "prompt_chars": _prompt_char_count(probe),
        "score": 0.0,
        "passed": False,
        "reason": "请求失败，无法评价该探针。",
    }


def _score_results(
    claimed_model: str,
    probe_results: list[dict[str, Any]],
    baselines: dict[str, BaselineModelStats] | None = None,
) -> dict[str, Any]:
    baselines = baselines or {}
    total = len(probe_results) or 1
    successes = [result for result in probe_results if result.get("ok")]
    success_ratio = len(successes) / total
    if not successes:
        first_error = next((result.get("error") for result in probe_results if result.get("error")), "无响应")
        return {
            "scores": {
                "protocol_score": 0.0,
                "capability_score": 0.0,
                "behavior_score": 0.0,
                "stability_score": 0.0,
                "success_ratio": 0.0,
            },
            "claim_consistency": "unavailable",
            "confidence": "none",
            "top_matches": [],
            "evidence": [
                f"成功请求 0/{total} 个探针。",
                f"首个错误：{first_error}",
                "没有成功响应，因此不会输出模型概率判断。",
            ],
            "baseline": {
                "loaded": bool(baselines),
                "model_count": len(baselines),
                "models": sorted(baselines.keys()),
            },
            "model_profile": _model_profile_summary(claimed_model, Counter()),
            "success_count": 0,
        }

    scored = [float(result.get("score", 0.0)) for result in successes]
    capability_score = sum(scored) / len(scored) if scored else 0.0

    observed_models = [str(result.get("self_reported_model", "")) for result in successes if result.get("self_reported_model")]
    model_counts = Counter(observed_models)
    normalized_claim = _normalize_model_name(claimed_model)
    matching_models = [
        model for model in observed_models if _normalize_model_name(model) == normalized_claim
    ]
    protocol_score = len(matching_models) / len(observed_models) if observed_models else 0.0
    stability_score = 1.0 if len(model_counts) <= 1 and successes else 0.4 if successes else 0.0
    model_profile = _model_profile_summary(claimed_model, model_counts)
    profile_score = _profile_score(model_profile)

    max_claim_probability = 0.985 if protocol_score == 1.0 and success_ratio == 1.0 else 0.92
    claim_probability = _clamp(
        0.10
        + 0.42 * protocol_score
        + 0.28 * capability_score
        + 0.08 * profile_score
        + 0.08 * success_ratio
        + 0.04 * stability_score,
        0.02,
        max_claim_probability,
    )

    baseline_matches = _baseline_matches(probe_results, baselines)
    scoring_method = "baseline" if baseline_matches else "heuristic"
    if baseline_matches:
        top_matches = baseline_matches
    else:
        top_matches = [{"model": claimed_model, "probability": round(claim_probability, 3)}]
    most_common_observed = model_counts.most_common(1)[0][0] if model_counts else ""
    if not baseline_matches and most_common_observed and _normalize_model_name(most_common_observed) != normalized_claim:
        observed_probability = _clamp(0.25 + 0.35 * (model_counts[most_common_observed] / len(observed_models)), 0.1, 0.75)
        top_matches.append({"model": most_common_observed, "probability": round(observed_probability, 3)})

    used_probability = sum(item["probability"] for item in top_matches)
    min_unknown_probability = 0.015 if protocol_score == 1.0 and success_ratio == 1.0 else 0.05
    unknown_probability = round(max(min_unknown_probability, 1.0 - used_probability), 3)
    top_matches.append({"model": "unknown/out-of-set", "probability": unknown_probability})
    top_matches = _normalize_probabilities(top_matches)

    final_claim_probability = _claim_probability_from_matches(claimed_model, top_matches) if baseline_matches else claim_probability
    claim_consistency = "high" if final_claim_probability >= 0.70 else "medium" if final_claim_probability >= 0.45 else "low"
    confidence = _confidence(total, success_ratio)

    evidence = [
        f"成功请求 {len(successes)}/{total} 个探针。",
        f"API 自报模型集合：{', '.join(model_counts.keys()) if model_counts else '无'}。",
        f"协议一致性分数：{protocol_score:.2f}。",
        f"模型族一致性：{model_profile['family_consistency']}。",
        f"能力探针平均分：{capability_score:.2f}。",
    ]
    if observed_models and not matching_models:
        evidence.append("API 自报模型与声称模型不一致，这是强可疑信号。")
    if success_ratio < 1:
        evidence.append("部分请求失败，置信度会降低。")
    if baselines:
        evidence.append(f"已加载 {len(baselines)} 个模型基线参与比较。")
        evidence.append("当前优先使用基线相似度生成模型匹配概率。")
    else:
        evidence.append("未加载可选基线，当前使用协议特征、行为探针和模型画像的轻量评分。")
    if protocol_score == 1.0 and success_ratio == 1.0:
        evidence.append("API 可访问，且自报模型与填写模型完全一致。")

    return {
        "scores": {
            "protocol_score": round(protocol_score, 3),
            "capability_score": round(capability_score, 3),
            "behavior_score": round(profile_score, 3),
            "stability_score": round(stability_score, 3),
            "success_ratio": round(success_ratio, 3),
            "scoring_method": scoring_method,
        },
        "claim_consistency": claim_consistency,
        "confidence": confidence,
        "top_matches": top_matches,
        "evidence": evidence,
        "baseline": {
            "loaded": bool(baselines),
            "model_count": len(baselines),
            "models": sorted(baselines.keys()),
            "captured_at_min": min((item.captured_at_min for item in baselines.values() if item.captured_at_min), default=""),
            "captured_at_max": max((item.captured_at_max for item in baselines.values() if item.captured_at_max), default=""),
        },
        "model_profile": model_profile,
        "success_count": len(successes),
    }


def _normalize_model_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_probabilities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(item["probability"]) for item in items) or 1.0
    normalized = [
        {"model": item["model"], "probability": round(float(item["probability"]) / total, 3)}
        for item in items
    ]
    return sorted(normalized, key=lambda item: item["probability"], reverse=True)


def _claim_probability_from_matches(claimed_model: str, matches: list[dict[str, Any]]) -> float:
    normalized_claim = _normalize_model_name(claimed_model)
    for item in matches:
        if _normalize_model_name(str(item.get("model", ""))) == normalized_claim:
            return float(item.get("probability", 0.0))
    return 0.0


def _model_profile_summary(claimed_model: str, model_counts: Counter[str]) -> dict[str, Any]:
    claimed_match = match_model_profile(claimed_model)
    observed = []
    for model, count in model_counts.most_common():
        observed_match = match_model_profile(model)
        item = profile_match_to_dict(observed_match)
        item["model"] = model
        item["count"] = count
        observed.append(item)

    claimed = profile_match_to_dict(claimed_match)
    claimed["model"] = claimed_model
    family_consistency = _family_consistency(claimed, observed)
    return {
        "claimed": claimed,
        "observed": observed,
        "family_consistency": family_consistency,
    }


def _family_consistency(claimed: dict[str, Any], observed: list[dict[str, Any]]) -> str:
    claimed_family = str(claimed.get("family", "unknown"))
    observed_families = {str(item.get("family", "unknown")) for item in observed if item.get("family") != "unknown"}
    if not observed:
        return "unknown"
    if claimed_family == "unknown" or not observed_families:
        return "unknown"
    if observed_families == {claimed_family}:
        return "same_family"
    if claimed_family in observed_families:
        return "mixed"
    return "different_family"


def _profile_score(model_profile: dict[str, Any]) -> float:
    consistency = model_profile.get("family_consistency")
    if consistency == "same_family":
        return 1.0
    if consistency == "mixed":
        return 0.6
    if consistency == "different_family":
        return 0.0
    return 0.5


def _confidence(total: int, success_ratio: float) -> str:
    if total >= 7 and success_ratio >= 0.9:
        return "high"
    if total >= 5 and success_ratio >= 0.7:
        return "medium"
    if total >= 3 and success_ratio >= 0.7:
        return "medium"
    return "low"


def _baseline_matches(
    probe_results: list[dict[str, Any]],
    baselines: dict[str, BaselineModelStats],
) -> list[dict[str, Any]]:
    if not baselines:
        return []

    observed_scores = {
        str(result.get("probe_id")): float(result.get("score", 0.0))
        for result in probe_results
        if result.get("ok") and result.get("probe_id")
    }
    if not observed_scores:
        return []

    similarities = []
    for model, stats in baselines.items():
        shared = set(observed_scores).intersection(stats.probe_scores)
        if not shared:
            continue
        diffs = [abs(observed_scores[probe_id] - stats.probe_scores[probe_id]) for probe_id in shared]
        similarity = _clamp(1.0 - (sum(diffs) / len(diffs)), 0.01, 0.98)
        coverage_bonus = min(0.08, len(shared) / max(1, len(observed_scores)) * 0.08)
        similarities.append((model, similarity + coverage_bonus))

    if not similarities:
        return []

    similarities.sort(key=lambda item: item[1], reverse=True)
    raw = [{"model": model, "probability": round(score, 3)} for model, score in similarities[:5]]
    return _normalize_probabilities(raw)


def _risk_checks(
    claimed_model: str,
    probe_results: list[dict[str, Any]],
    stream_result: dict[str, Any] | None,
    error_probe_result: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "model_identity": _model_identity_check(claimed_model, probe_results),
        "token_injection": _token_injection_check(probe_results),
        "context_truncation": _probe_check(
            probe_results,
            "risk.context.canary",
            clean_reason="长上下文 canary 标记均被正确返回，未发现明显截断。",
            anomaly_reason="长上下文 canary 标记缺失，可能存在上下文截断或中转层改写。",
            inconclusive_reason="当前检测强度未运行上下文截断探针，或没有可用结果。",
        ),
        "error_leakage": _error_leakage_check(probe_results, stream_result, error_probe_result),
        "response_rewriting": _probe_check(
            probe_results,
            "risk.response_rewriting.echo",
            clean_reason="固定字符串和包名被正确返回，未发现明显响应改写。",
            anomaly_reason="固定字符串或包名未被正确返回，可能存在响应改写或模型未遵循指令。",
            inconclusive_reason="当前检测强度未运行响应改写探针，或没有可用结果。",
        ),
        "stream_integrity": _stream_integrity_check(stream_result),
    }


def _model_identity_check(claimed_model: str, probe_results: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [result for result in probe_results if result.get("ok")]
    observed_models = [
        str(result.get("self_reported_model", ""))
        for result in successes
        if result.get("self_reported_model")
    ]
    if not observed_models:
        return {
            "status": CHECK_INCONCLUSIVE,
            "summary": "没有成功响应，无法判断模型身份。",
            "evidence": [],
        }

    normalized_claim = _normalize_model_name(claimed_model)
    exact_matches = [model for model in observed_models if _normalize_model_name(model) == normalized_claim]
    profile = _model_profile_summary(claimed_model, Counter(observed_models))
    consistency = profile["family_consistency"]
    evidence = [
        f"声称模型：{claimed_model}",
        f"API 自报模型：{', '.join(Counter(observed_models).keys())}",
        f"模型族一致性：{consistency}",
    ]
    if len(exact_matches) == len(observed_models):
        return {
            "status": CHECK_CLEAN,
            "summary": "API 自报模型与声称模型一致。",
            "evidence": evidence,
        }
    if consistency == "different_family":
        return {
            "status": CHECK_ANOMALY,
            "summary": "API 自报模型与声称模型属于不同模型族。",
            "evidence": evidence,
        }
    return {
        "status": CHECK_INCONCLUSIVE,
        "summary": "API 自报模型与声称模型不完全一致，但暂未形成强异常。",
        "evidence": evidence,
    }


def _token_injection_check(probe_results: list[dict[str, Any]]) -> dict[str, Any]:
    inspected = []
    anomalies = []
    threshold_multiplier = 8
    absolute_floor = 900
    for result in probe_results:
        if not result.get("ok"):
            continue
        usage = result.get("usage", {})
        if not isinstance(usage, dict):
            continue
        prompt_tokens = _prompt_tokens_from_usage(usage)
        if prompt_tokens is None:
            continue
        expected_upper = _expected_prompt_token_upper_bound(int(result.get("prompt_chars", 0) or 0))
        inspected.append((str(result.get("probe_id", "")), prompt_tokens, expected_upper))
        if prompt_tokens > max(absolute_floor, expected_upper * threshold_multiplier):
            anomalies.append((str(result.get("probe_id", "")), prompt_tokens, expected_upper))

    if anomalies:
        evidence = [
            f"{probe_id}: prompt/input tokens={prompt_tokens}, 参考上限={expected_upper}"
            for probe_id, prompt_tokens, expected_upper in anomalies[:5]
        ]
        return {
            "status": CHECK_ANOMALY,
            "summary": "usage 中的输入 token 明显高于轻量探针预期，可能存在隐藏 prompt 注入。",
            "evidence": evidence,
            "threshold": {
                "rule": "prompt_tokens > max(absolute_floor, expected_upper * threshold_multiplier)",
                "absolute_floor": absolute_floor,
                "threshold_multiplier": threshold_multiplier,
            },
            "inspected_count": len(inspected),
        }
    if inspected:
        max_item = max(inspected, key=lambda item: item[1])
        max_seen = max_item[1]
        max_expected = max_item[2]
        return {
            "status": CHECK_CLEAN,
            "summary": "未发现明显异常的输入 token 增量。",
            "evidence": [
                f"已检查 {len(inspected)} 个 usage 记录，最大输入 token={max_seen}。",
                f"最高参考上限={max_expected}，异常阈值=max({absolute_floor}, 参考上限*{threshold_multiplier})。",
            ],
            "threshold": {
                "rule": "prompt_tokens > max(absolute_floor, expected_upper * threshold_multiplier)",
                "absolute_floor": absolute_floor,
                "threshold_multiplier": threshold_multiplier,
                "max_expected_upper": max_expected,
            },
            "inspected_count": len(inspected),
            "max_prompt_tokens": max_seen,
        }
    return {
        "status": CHECK_INCONCLUSIVE,
        "summary": "响应中没有可用 usage token 信息，无法判断 token 注入。",
        "evidence": [],
    }


def _prompt_tokens_from_usage(usage: dict[str, Any]) -> int | None:
    for key in ("prompt_tokens", "input_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return None


def _expected_prompt_token_upper_bound(prompt_chars: int) -> int:
    # We do not have provider tokenizers here. Use a loose upper bound to avoid false positives.
    char_count = prompt_chars + 420
    return max(160, int(char_count / 1.5))


def _probe_check(
    probe_results: list[dict[str, Any]],
    probe_id: str,
    *,
    clean_reason: str,
    anomaly_reason: str,
    inconclusive_reason: str,
) -> dict[str, Any]:
    result = next((item for item in probe_results if item.get("probe_id") == probe_id), None)
    if result is None:
        return {
            "status": CHECK_INCONCLUSIVE,
            "summary": inconclusive_reason,
            "evidence": [],
        }
    if result.get("ok") and result.get("passed"):
        return {
            "status": CHECK_CLEAN,
            "summary": clean_reason,
            "evidence": [str(result.get("reason", ""))],
        }
    if result.get("ok"):
        return {
            "status": CHECK_ANOMALY,
            "summary": anomaly_reason,
            "evidence": [str(result.get("reason", "")), f"样本：{result.get('sample', '')}"],
        }
    return {
        "status": CHECK_INCONCLUSIVE,
        "summary": inconclusive_reason,
        "evidence": [str(result.get("error", ""))],
    }


def _error_leakage_check(
    probe_results: list[dict[str, Any]],
    stream_result: dict[str, Any] | None,
    error_probe_result: dict[str, Any] | None,
) -> dict[str, Any]:
    failures = [result for result in probe_results if not result.get("ok")]
    leaked = [result for result in failures if result.get("sensitive_leak_detected")]
    if stream_result and stream_result.get("sensitive_leak_detected"):
        leaked.append({"probe_id": "stream_integrity", "error": stream_result.get("error", "")})
    if error_probe_result and error_probe_result.get("sensitive_leak_detected"):
        leaked.append({"probe_id": "risk.error.invalid_model", "error": error_probe_result.get("error", "")})
    if leaked:
        return {
            "status": CHECK_ANOMALY,
            "summary": "错误响应疑似回显了 API key 或敏感凭证，报告已自动脱敏。",
            "evidence": [f"{item.get('probe_id', '')}: {item.get('error', '')}" for item in leaked[:3]],
        }
    if error_probe_result:
        if not error_probe_result.get("ok"):
            return {
                "status": CHECK_CLEAN,
                "summary": "专门错误探针未发现 API key 原样回显。",
                "evidence": [str(error_probe_result.get("reason", "")), str(error_probe_result.get("error", ""))],
            }
        return {
            "status": CHECK_INCONCLUSIVE,
            "summary": "无效模型名请求被服务端接受，没有产生可检查的错误响应。",
            "evidence": [str(error_probe_result.get("reason", ""))],
        }
    if failures:
        return {
            "status": CHECK_CLEAN,
            "summary": "已检查失败响应，未发现 API key 原样回显。",
            "evidence": [f"已检查 {len(failures)} 个失败响应。"],
        }
    return {
        "status": CHECK_INCONCLUSIVE,
        "summary": "没有失败响应可供检查，尚未运行专门的错误泄漏探针。",
        "evidence": [],
    }


def _stream_integrity_check(stream_result: dict[str, Any] | None) -> dict[str, Any]:
    if stream_result is None:
        return {
            "status": CHECK_INCONCLUSIVE,
            "summary": "当前检测强度未运行 stream 完整性检查，或普通探针没有成功响应。",
            "evidence": [],
        }
    if not stream_result.get("ok"):
        return {
            "status": CHECK_INCONCLUSIVE,
            "summary": "stream 请求失败，无法判断流式完整性。",
            "evidence": [str(stream_result.get("error", ""))],
        }
    evidence = [
        f"event_count={stream_result.get('event_count', 0)}",
        f"done_seen={stream_result.get('done_seen', False)}",
        f"finish_seen={stream_result.get('finish_seen', False)}",
        f"content_type={stream_result.get('content_type', '')}",
    ]
    if stream_result.get("raw_event_types"):
        evidence.append(f"event_types={', '.join(str(item) for item in stream_result.get('raw_event_types', []))}")
    if stream_result.get("event_type_counts"):
        evidence.append(f"event_type_counts={stream_result.get('event_type_counts')}")
    if stream_result.get("passed"):
        return {
            "status": CHECK_CLEAN,
            "summary": "stream 响应包含有效事件、目标内容和结束信号。",
            "evidence": evidence,
        }
    return {
        "status": CHECK_ANOMALY,
        "summary": "stream 响应缺少目标内容或结束信号，可能存在流式包装异常。",
        "evidence": evidence + [f"样本：{stream_result.get('sample', '')}"],
    }


def _behavior_fingerprint(probe_results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[float]] = {
        "format_following": [],
        "reasoning": [],
        "code": [],
        "chinese": [],
        "risk": [],
        "general": [],
    }
    for result in probe_results:
        if not result.get("ok"):
            continue
        probe_id = str(result.get("probe_id", ""))
        title = str(result.get("title", ""))
        score = float(result.get("score", 0.0))
        group = _behavior_group(probe_id, title)
        groups.setdefault(group, []).append(score)

    result: dict[str, Any] = {}
    for group, scores in groups.items():
        result[group] = {
            "score": round(sum(scores) / len(scores), 3) if scores else None,
            "probe_count": len(scores),
        }
    populated = [item["score"] for item in result.values() if isinstance(item.get("score"), float)]
    result["overall"] = {
        "score": round(sum(populated) / len(populated), 3) if populated else None,
        "probe_count": sum(int(item.get("probe_count", 0)) for item in result.values() if isinstance(item, dict)),
    }
    return result


def _behavior_group(probe_id: str, title: str) -> str:
    key = f"{probe_id} {title}".lower()
    if "risk." in key:
        return "risk"
    if "json" in key or "format" in key or "marker" in key or "lines" in key or "instruction" in key:
        return "format_following"
    if "math" in key or "logic" in key or "rank" in key:
        return "reasoning"
    if "code" in key or "python" in key:
        return "code"
    if "chinese" in key or "中文" in key or "zh_" in key or ".zh" in key:
        return "chinese"
    return "general"


def _family_likelihoods(
    api_type: str,
    model_profile: dict[str, Any],
    checks: dict[str, Any],
    behavior_fingerprint: dict[str, Any],
) -> list[dict[str, Any]]:
    scores = {
        "gpt": 0.08,
        "claude": 0.08,
        "deepseek": 0.08,
        "kimi": 0.06,
        "glm": 0.06,
        "minimax": 0.06,
        "unknown/out-of-set": 0.22,
    }

    claimed = model_profile.get("claimed", {}) if isinstance(model_profile, dict) else {}
    observed = model_profile.get("observed", []) if isinstance(model_profile, dict) else []
    claimed_family = str(claimed.get("family", "unknown")) if isinstance(claimed, dict) else "unknown"
    if claimed_family in scores:
        scores[claimed_family] += 0.16

    if isinstance(observed, list):
        total_count = sum(int(item.get("count", 0)) for item in observed if isinstance(item, dict)) or 1
        for item in observed:
            if not isinstance(item, dict):
                continue
            family = str(item.get("family", "unknown"))
            if family in scores:
                scores[family] += 0.46 * (int(item.get("count", 0)) / total_count)

    if api_type == "anthropic":
        scores["claude"] += 0.12
    elif api_type == "openai-compatible":
        scores["gpt"] += 0.04

    model_identity = checks.get("model_identity", {}) if isinstance(checks, dict) else {}
    if isinstance(model_identity, dict) and model_identity.get("status") == CHECK_ANOMALY:
        scores["unknown/out-of-set"] += 0.16

    overall = behavior_fingerprint.get("overall", {}) if isinstance(behavior_fingerprint, dict) else {}
    if isinstance(overall, dict) and isinstance(overall.get("score"), float):
        score = float(overall["score"])
        if score < 0.45:
            scores["unknown/out-of-set"] += 0.10

    total = sum(scores.values()) or 1.0
    result = [
        {
            "family": family,
            "probability": round(value / total, 3),
            "method": "heuristic-profile",
        }
        for family, value in scores.items()
    ]
    return sorted(result, key=lambda item: item["probability"], reverse=True)


def _risk_level(checks: dict[str, Any]) -> str:
    statuses = [
        str(item.get("status", CHECK_INCONCLUSIVE))
        for item in checks.values()
        if isinstance(item, dict)
    ]
    anomaly_count = statuses.count(CHECK_ANOMALY)
    if anomaly_count >= 2:
        return "high"
    if anomaly_count == 1:
        return "medium"
    if statuses and all(status == CHECK_CLEAN for status in statuses):
        return "low"
    if CHECK_CLEAN in statuses:
        return "low"
    return "unknown"


def _contains_sensitive(text: str, api_key: str) -> bool:
    return bool(api_key and len(api_key) >= 8 and api_key in text)


def _redact_sensitive(text: str, api_key: str) -> str:
    if not api_key:
        return text
    redacted = _mask_secret(api_key)
    return text.replace(api_key, redacted)


def _prompt_char_count(probe: Probe) -> int:
    return sum(len(item.get("content", "")) for item in probe.messages())


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def _diagnostics(config: AuditConfig, probe_results: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [str(result.get("error")) for result in probe_results if result.get("error")]
    status_codes = [result.get("status_code") for result in probe_results if result.get("status_code") is not None]
    hints = list(base_url_warnings(config.base_url, config.api_type))
    suggested_models: list[str] = []
    if errors:
        first = errors[0]
        all_errors = "\n".join(errors)
        if "HTTP 401" in all_errors or "HTTP 403" in all_errors:
            hints.append("认证失败：请检查 API key 是否有效，或该 key 是否有权限访问该模型。")
        if "HTTP 404" in all_errors:
            hints.append("地址或路径可能不对：OpenAI-compatible 通常填写到 /v1，Anthropic 通常填写到 /v1。")
        if "HTTP 400" in all_errors:
            hints.append("API 已响应，但请求参数被拒绝：请优先检查模型名、API 类型或中转站兼容性。")
            suggested_models = _extract_model_suggestions(all_errors)
            if suggested_models:
                hints.append(f"错误信息中提到的可用模型名：{', '.join(suggested_models)}。")
        if "response is not valid JSON" in all_errors:
            hints.append("服务器返回的不是 API JSON，通常说明你填的是网站首页地址，而不是 API Base URL。")
            hints.append("请在中转站文档中寻找 API Base URL；OpenAI-compatible 常见结尾是 /v1，Anthropic 常见结尾是 /v1 或 /anthropic。")
        if "request failed" in all_errors:
            hints.append("网络连接失败：请检查 base_url 是否可访问，或本机代理/网络设置。")
    return {
        "effective_base_url": normalize_base_url(config.base_url, config.api_type),
        "first_error": errors[0] if errors else "",
        "error_count": len(errors),
        "status_codes": status_codes,
        "suggested_models": suggested_models,
        "hints": hints,
    }


def _status_from_scores(scores: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    if scores.get("success_count", 0) > 0:
        return "completed"
    status_codes = diagnostics.get("status_codes", [])
    if status_codes and all(code in {401, 403} for code in status_codes):
        return "auth_error"
    if status_codes and any(code == 400 for code in status_codes) and all(code in {400, None} for code in status_codes):
        return "request_error"
    return "endpoint_error"


def _message_for_status(status: str) -> str:
    if status == "completed":
        return "检测已完成。本报告是概率判断，不是绝对证明。"
    if status == "auth_error":
        return "API 已响应，但认证失败，尚未产生模型判断。请检查 API key 和权限。"
    if status == "request_error":
        return "API 已响应，但请求参数被拒绝，尚未产生模型判断。请检查模型名和 API 类型。"
    return "无法访问该 API endpoint，尚未产生模型判断。请先检查 API 地址、协议类型、Key、模型名和网络。"


def _extract_model_suggestions(text: str) -> list[str]:
    candidates = re.findall(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){1,}\b", text, flags=re.IGNORECASE)
    ignored = {
        "invalid-request-error",
        "chat-completions",
        "api-key",
        "base-url",
    }
    result = []
    for item in candidates:
        normalized = item.strip(".,;:，。；：")
        if normalized.lower() in ignored:
            continue
        if normalized not in result:
            result.append(normalized)
    return result[:8]
