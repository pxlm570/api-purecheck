from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any


def emit_report(report: dict[str, Any], output_format: str, output: str | None) -> None:
    text = format_report(report, output_format)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def format_report(report: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if output_format == "html":
        return format_html_report(report)
    if output_format in {"markdown", "md"}:
        return format_markdown_report(report)
    return format_text_report(report)


def format_text_report(report: dict[str, Any]) -> str:
    config = report.get("config", {})
    if not isinstance(config, dict):
        config = {}

    lines = [
        "API PureCheck 纯度报告",
        "",
        f"状态：{report.get('status', 'unknown')}",
        f"说明：{report.get('message', '')}",
        f"API 地址：{config.get('base_url', '')}",
        f"API Key：{config.get('api_key', '')}",
        f"声称模型：{config.get('claimed_model', '')}",
        f"检测强度：{config.get('level', '')}",
    ]

    if "estimated_request_count" in report:
        lines.append(f"预计请求数：{report['estimated_request_count']}")

    if "claim_consistency" in report:
        lines.extend(
            [
                "",
                f"纯度结论：{_label_consistency(report.get('claim_consistency'))}",
                f"报告置信度：{_label_confidence(report.get('confidence'))}",
                f"总体风险：{_label_risk(report.get('risk_level', 'unknown'))}",
                "最可能匹配：",
            ]
        )
        for item in report.get("top_matches", []):
            if isinstance(item, dict):
                probability = float(item.get("probability", 0.0))
                lines.append(f"- {_display_model_label(item.get('model'))}: {probability:.1%}")

    profile_lines = _text_model_profile(report.get("model_profile"))
    if profile_lines:
        lines.extend(["", "模型族画像：", *profile_lines])

    check_lines = _text_checks(report.get("checks"))
    if check_lines:
        lines.extend(["", "风险检查：", *check_lines])

    fingerprint_lines = _text_behavior_fingerprint(report.get("behavior_fingerprint"))
    if fingerprint_lines:
        lines.extend(["", "行为画像：", *fingerprint_lines])

    family_lines = _text_family_likelihoods(report.get("family_likelihoods"))
    if family_lines:
        lines.extend(["", "模型族倾向：", *family_lines])

    evidence = report.get("evidence", [])
    if evidence:
        lines.extend(["", "主要证据："])
        for item in evidence:
            lines.append(f"- {item}")

    limitations = report.get("limitations", [])
    if limitations:
        lines.extend(["", "局限说明："])
        for item in limitations:
            lines.append(f"- {item}")

    return "\n".join(lines)


def format_markdown_report(report: dict[str, Any]) -> str:
    config = report.get("config", {})
    if not isinstance(config, dict):
        config = {}

    lines = [
        "# API PureCheck 纯度报告",
        "",
        f"- 状态：`{report.get('status', 'unknown')}`",
        f"- 说明：{report.get('message', '')}",
        f"- API 地址：`{config.get('base_url', '')}`",
        f"- API Key：`{config.get('api_key', '')}`",
        f"- 声称模型：`{config.get('claimed_model', '')}`",
        f"- 检测强度：`{config.get('level', '')}`",
    ]

    if "claim_consistency" in report:
        lines.extend(
            [
                "",
                "## 结论",
                "",
                f"- 纯度结论：`{_label_consistency(report.get('claim_consistency'))}`",
                f"- 报告置信度：`{_label_confidence(report.get('confidence'))}`",
                f"- 总体风险：`{_label_risk(report.get('risk_level', 'unknown'))}`",
            ]
        )

    matches = report.get("top_matches", [])
    if isinstance(matches, list) and matches:
        lines.extend(["", "## 最可能匹配", "", "| 模型 | 概率 |", "| --- | ---: |"])
        for item in matches:
            if isinstance(item, dict):
                probability = float(item.get("probability", 0.0))
                lines.append(f"| `{_display_model_label(item.get('model'))}` | {probability:.1%} |")

    profile_lines = _text_model_profile(report.get("model_profile"))
    if profile_lines:
        lines.extend(["", "## 模型族画像", ""])
        lines.extend(profile_lines)

    check_lines = _text_checks(report.get("checks"))
    if check_lines:
        lines.extend(["", "## 风险检查", ""])
        lines.extend(check_lines)

    fingerprint_lines = _text_behavior_fingerprint(report.get("behavior_fingerprint"))
    if fingerprint_lines:
        lines.extend(["", "## 行为画像", ""])
        lines.extend(fingerprint_lines)

    family_lines = _text_family_likelihoods(report.get("family_likelihoods"))
    if family_lines:
        lines.extend(["", "## 模型族倾向", ""])
        lines.extend(family_lines)

    evidence = report.get("evidence", [])
    if evidence:
        lines.extend(["", "## 主要证据", ""])
        for item in evidence:
            lines.append(f"- {item}")

    limitations = report.get("limitations", [])
    if limitations:
        lines.extend(["", "## 局限说明", ""])
        for item in limitations:
            lines.append(f"- {item}")

    return "\n".join(lines)


def format_html_report(report: dict[str, Any]) -> str:
    config = report.get("config", {})
    if not isinstance(config, dict):
        config = {}
    matches = report.get("top_matches", [])
    evidence = report.get("evidence", [])
    limitations = report.get("limitations", [])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>API PureCheck 纯度报告</title>
  <style>
    body {{
      margin: 0;
      background: #f7f8fb;
      color: #151922;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }}
    h2 {{ margin: 24px 0 10px; font-size: 20px; letter-spacing: 0; }}
    .panel {{
      background: #fff;
      border: 1px solid #d8dee8;
      border-radius: 8px;
      padding: 18px;
      margin-top: 16px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }}
    .item {{
      border: 1px solid #e4e9f1;
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfe;
    }}
    .label {{ color: #637083; font-size: 13px; }}
    .value {{ font-weight: 700; overflow-wrap: anywhere; }}
    .bar {{
      height: 10px;
      background: #e8edf4;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 6px;
    }}
    .bar span {{ display: block; height: 100%; background: #1457d9; }}
    li {{ margin: 6px 0; }}
    pre {{
      overflow: auto;
      max-height: 420px;
      padding: 12px;
      border-radius: 6px;
      background: #101827;
      color: #e7edf7;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>API PureCheck 纯度报告</h1>
    <p>{escape(str(report.get("message", "")))}</p>
    <section class="panel">
      <div class="meta">
        {html_meta_item("状态", report.get("status", ""))}
        {html_meta_item("API 地址", config.get("base_url", ""))}
        {html_meta_item("API Key", config.get("api_key", ""))}
        {html_meta_item("声称模型", config.get("claimed_model", ""))}
        {html_meta_item("检测强度", config.get("level", ""))}
        {html_meta_item("纯度结论", _label_consistency(report.get("claim_consistency", "未检测")))}
        {html_meta_item("报告置信度", _label_confidence(report.get("confidence", "未检测")))}
        {html_meta_item("总体风险", _label_risk(report.get("risk_level", "unknown")))}
      </div>
    </section>
    {html_model_profile(report.get("model_profile"))}
    {html_checks(report.get("checks"))}
    {html_behavior_fingerprint(report.get("behavior_fingerprint"))}
    {html_family_likelihoods(report.get("family_likelihoods"))}
    {html_matches(matches)}
    {html_list("主要证据", evidence)}
    {html_list("局限说明", limitations)}
    <section class="panel">
      <h2>完整 JSON</h2>
      <pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
    </section>
  </main>
</body>
</html>"""


def html_meta_item(label: str, value: object) -> str:
    return (
        '<div class="item">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(str(value))}</div>'
        "</div>"
    )


def html_matches(matches: object) -> str:
    if not isinstance(matches, list) or not matches:
        return ""
    rows = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        probability = float(item.get("probability", 0.0))
        pct = max(0.0, min(100.0, probability * 100.0))
        rows.append(
            "<li>"
            f"<strong>{escape(_display_model_label(item.get('model')))}</strong>: {pct:.1f}%"
            f'<div class="bar"><span style="width: {pct:.1f}%"></span></div>'
            "</li>"
        )
    return '<section class="panel"><h2>最可能匹配</h2><ul>' + "".join(rows) + "</ul></section>"


def html_model_profile(model_profile: object) -> str:
    if not isinstance(model_profile, dict):
        return ""
    claimed = model_profile.get("claimed", {})
    observed = model_profile.get("observed", [])
    if not isinstance(claimed, dict):
        claimed = {}
    if not isinstance(observed, list):
        observed = []
    rows = [
        html_meta_item("声称模型族", _profile_label(claimed)),
        html_meta_item("模型族一致性", model_profile.get("family_consistency", "unknown")),
    ]
    observed_items = []
    for item in observed:
        if isinstance(item, dict):
            observed_items.append(
                f"{escape(str(item.get('model', '')))} "
                f"({escape(str(item.get('display_name', item.get('family', 'unknown'))))}, "
                f"{escape(str(item.get('count', 0)))} 次)"
            )
    observed_html = "".join(f"<li>{item}</li>" for item in observed_items) or "<li>无</li>"
    return (
        '<section class="panel"><h2>模型族画像</h2>'
        '<div class="meta">'
        + "".join(rows)
        + "</div>"
        + "<ul>"
        + observed_html
        + "</ul></section>"
    )


def html_checks(checks: object) -> str:
    if not isinstance(checks, dict) or not checks:
        return ""
    rows = []
    for name, item in checks.items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "inconclusive"))
        summary = str(item.get("summary", ""))
        rows.append(
            "<li>"
            f"<strong>{escape(str(name))}</strong>: {escape(status)}"
            f"<div>{escape(summary)}</div>"
            "</li>"
        )
    if not rows:
        return ""
    return '<section class="panel"><h2>风险检查</h2><ul>' + "".join(rows) + "</ul></section>"


def html_behavior_fingerprint(fingerprint: object) -> str:
    if not isinstance(fingerprint, dict) or not fingerprint:
        return ""
    rows = []
    for name, item in fingerprint.items():
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        probe_count = item.get("probe_count", 0)
        score_text = "n/a" if score is None else f"{float(score):.2f}"
        rows.append(f"<li><strong>{escape(str(name))}</strong>: {escape(score_text)} ({escape(str(probe_count))} probes)</li>")
    if not rows:
        return ""
    return '<section class="panel"><h2>行为画像</h2><ul>' + "".join(rows) + "</ul></section>"


def html_family_likelihoods(items: object) -> str:
    if not isinstance(items, list) or not items:
        return ""
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        probability = float(item.get("probability", 0.0))
        rows.append(f"<li><strong>{escape(_display_model_label(item.get('family')))}</strong>: {probability:.1%}</li>")
    if not rows:
        return ""
    return '<section class="panel"><h2>模型族倾向</h2><ul>' + "".join(rows) + "</ul></section>"


def _text_model_profile(model_profile: object) -> list[str]:
    if not isinstance(model_profile, dict):
        return []
    claimed = model_profile.get("claimed", {})
    observed = model_profile.get("observed", [])
    if not isinstance(claimed, dict):
        claimed = {}
    if not isinstance(observed, list):
        observed = []

    lines = [
        f"- 声称模型族：{_profile_label(claimed)}",
        f"- 模型族一致性：{model_profile.get('family_consistency', 'unknown')}",
    ]
    if observed:
        observed_text = []
        for item in observed:
            if isinstance(item, dict):
                observed_text.append(
                    f"{item.get('model', '')} ({item.get('display_name', item.get('family', 'unknown'))}, {item.get('count', 0)} 次)"
                )
        if observed_text:
            lines.append(f"- API 自报模型族：{'; '.join(observed_text)}")
    return lines


def _text_checks(checks: object) -> list[str]:
    if not isinstance(checks, dict):
        return []
    lines = []
    for name, item in checks.items():
        if not isinstance(item, dict):
            continue
        status = item.get("status", "inconclusive")
        summary = item.get("summary", "")
        lines.append(f"- {name}: {status}。{summary}")
    return lines


def _text_behavior_fingerprint(fingerprint: object) -> list[str]:
    if not isinstance(fingerprint, dict):
        return []
    lines = []
    for name, item in fingerprint.items():
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        probe_count = item.get("probe_count", 0)
        score_text = "n/a" if score is None else f"{float(score):.2f}"
        lines.append(f"- {name}: {score_text} ({probe_count} probes)")
    return lines


def _text_family_likelihoods(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        probability = float(item.get("probability", 0.0))
        lines.append(f"- {_display_model_label(item.get('family'))}: {probability:.1%}")
    return lines


def _display_model_label(value: object) -> str:
    text = str(value or "")
    if text == "unknown/out-of-set":
        return "其他模型"
    return text


def _label_consistency(value: object) -> str:
    text = str(value or "")
    labels = {
        "high": "高度吻合",
        "medium": "需要复核",
        "low": "明显可疑",
        "unavailable": "不可判断",
        "未检测": "未检测",
    }
    return labels.get(text, text or "未检测")


def _label_confidence(value: object) -> str:
    text = str(value or "")
    labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无",
        "未检测": "未检测",
    }
    return labels.get(text, text or "未检测")


def _label_risk(value: object) -> str:
    text = str(value or "")
    labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "unknown": "未知",
    }
    return labels.get(text, text or "未知")


def _profile_label(item: dict[str, Any]) -> str:
    family = str(item.get("family", "unknown"))
    display_name = str(item.get("display_name", "unknown"))
    match_type = str(item.get("match_type", "none"))
    if family == "unknown":
        return "unknown"
    return f"{display_name} ({family}, {match_type})"


def html_list(title: str, items: object) -> str:
    if not isinstance(items, list) or not items:
        return ""
    rows = "".join(f"<li>{escape(str(item))}</li>" for item in items)
    return f'<section class="panel"><h2>{escape(title)}</h2><ul>{rows}</ul></section>'
