from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal


ValidatorKind = Literal["contains", "json_value", "contains_all", "none"]


@dataclass(frozen=True)
class Probe:
    probe_id: str
    title: str
    prompt: str
    validator: ValidatorKind
    expected: Any = None
    max_tokens: int = 256

    def messages(self) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": "你正在接受一个轻量 API 行为检测。请严格按用户要求回答，不要解释检测过程。",
            },
            {"role": "user", "content": self.prompt},
        ]


@dataclass(frozen=True)
class ProbeEvaluation:
    passed: bool
    score: float
    reason: str


def build_probes(level: str) -> list[Probe]:
    quick = [
        Probe(
            probe_id="math.addition.zh",
            title="中文简单数学",
            prompt="只输出最终数字，不要解释：17 + 25 = ?",
            validator="contains",
            expected="42",
            max_tokens=32,
        ),
        Probe(
            probe_id="format.strict_json",
            title="严格 JSON 输出",
            prompt='只输出一个 JSON 对象，格式必须是 {"answer":"purecheck"}，不要 Markdown。',
            validator="json_value",
            expected={"answer": "purecheck"},
            max_tokens=64,
        ),
        Probe(
            probe_id="logic.rank.zh",
            title="中文小型逻辑",
            prompt="只输出人名：小张比小李高，小王比小张高，三个人里谁最高？",
            validator="contains",
            expected="小王",
            max_tokens=32,
        ),
    ]

    standard_extra = [
        Probe(
            probe_id="instruction.no_extra_text",
            title="指令遵循",
            prompt="请只输出 PURECHECK_OK 这 12 个字符，不要添加任何其他内容。",
            validator="contains",
            expected="PURECHECK_OK",
            max_tokens=32,
        ),
    ]

    deep_extra = [
        Probe(
            probe_id="chinese.summary.constraint",
            title="中文约束摘要",
            prompt="把这句话压缩成 12 个字以内：这个工具用于检测中转站 API 是否像它声称的模型。只输出摘要。",
            validator="none",
            max_tokens=64,
        ),
        Probe(
            probe_id="code.boundary.python",
            title="代码边界条件",
            prompt=(
                "下面函数在空列表时会报错，请只输出修复后的 Python 函数代码，不要解释：\n"
                "def first_item(items):\n"
                "    return items[0]\n"
            ),
            validator="contains_all",
            expected=["def first_item", "if", "return"],
            max_tokens=160,
        ),
    ]

    standard_risk = risk_probes()
    standard_dynamic = dynamic_probes("standard", target_count=6 - len(quick) - len(standard_extra) - len(standard_risk))
    deep_dynamic = dynamic_probes(
        "deep",
        target_count=16 - len(quick) - len(standard_extra) - len(standard_risk) - len(standard_dynamic) - len(deep_extra),
    )

    if level == "quick":
        return quick
    if level == "standard":
        return quick + standard_extra + standard_risk + standard_dynamic
    if level == "deep":
        return quick + standard_extra + standard_risk + standard_dynamic + deep_extra + deep_dynamic
    raise ValueError("unknown probe level")


def risk_probes() -> list[Probe]:
    canary_start = "PC_CANARY_START_7F3A"
    canary_middle = "PC_CANARY_MIDDLE_9B2C"
    canary_end = "PC_CANARY_END_4D8E"
    filler = "稳定性测试文本。请忽略这句话，只定位标记。" * 80
    return [
        Probe(
            probe_id="risk.response_rewriting.echo",
            title="响应改写检查",
            prompt=(
                "请逐字输出下面这一行，不要改写、不要解释、不要加 Markdown：\n"
                "pip install requests==2.31.0 && echo PURECHECK_REWRITE_SENTINEL"
            ),
            validator="contains_all",
            expected=["pip install requests==2.31.0", "PURECHECK_REWRITE_SENTINEL"],
            max_tokens=96,
        ),
        Probe(
            probe_id="risk.context.canary",
            title="上下文截断检查",
            prompt=(
                f"下面是一段带标记的长文本。请只输出三个标记，用英文逗号分隔。\n"
                f"{canary_start}\n{filler}\n{canary_middle}\n{filler}\n{canary_end}"
            ),
            validator="contains_all",
            expected=[canary_start, canary_middle, canary_end],
            max_tokens=96,
        ),
    ]


def dynamic_probes(namespace: str, target_count: int) -> list[Probe]:
    probes: list[Probe] = []
    index = 1
    while len(probes) < target_count:
        a = 10 + index
        b = 20 + (index * 3 % 17)
        probes.append(
            Probe(
                probe_id=f"dynamic.{namespace}.math.{index}",
                title="动态数学",
                prompt=f"只输出最终数字，不要解释：{a} + {b} = ?",
                validator="contains",
                expected=str(a + b),
                max_tokens=32,
            )
        )
        if len(probes) >= target_count:
            break

        marker = f"PC_{namespace.upper()}_{index:02d}"
        probes.append(
            Probe(
                probe_id=f"dynamic.{namespace}.marker.{index}",
                title="动态标记输出",
                prompt=f"请只输出 {marker}，不要添加空格、标点或解释。",
                validator="contains",
                expected=marker,
                max_tokens=32,
            )
        )
        if len(probes) >= target_count:
            break

        json_expected = {"check": f"{namespace}-{index}", "value": index}
        probes.append(
            Probe(
                probe_id=f"dynamic.{namespace}.json.{index}",
                title="动态 JSON",
                prompt=f"只输出 JSON 对象，不要 Markdown：{json.dumps(json_expected, ensure_ascii=False)}",
                validator="json_value",
                expected=json_expected,
                max_tokens=80,
            )
        )
        if len(probes) >= target_count:
            break

        probes.append(
            Probe(
                probe_id=f"dynamic.{namespace}.zh_summary.{index}",
                title="动态中文约束",
                prompt=(
                    "把这句话压缩成 16 个字以内，只输出摘要："
                    f"第 {index} 组探针用于观察模型是否能稳定遵循中文格式约束。"
                ),
                validator="none",
                max_tokens=64,
            )
        )
        index += 1
    return probes


def load_probes_from_file(path: str | Path) -> list[Probe]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("probe file must be a JSON array")
    probes = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"probe item #{index + 1} must be an object")
        validator = str(item.get("validator", "none"))
        if validator not in {"contains", "json_value", "contains_all", "none"}:
            raise ValueError(f"probe {index + 1} validator is invalid")
        probes.append(
            Probe(
                probe_id=str(item.get("probe_id") or item.get("id") or f"custom.{index + 1}"),
                title=str(item.get("title") or f"自定义探针 {index + 1}"),
                prompt=str(item.get("prompt", "")),
                validator=validator,  # type: ignore[arg-type]
                expected=item.get("expected"),
                max_tokens=int(item.get("max_tokens", 256)),
            )
        )
    if not probes:
        raise ValueError("probe file must contain at least one probe")
    for probe in probes:
        if not probe.prompt:
            raise ValueError(f"probe {probe.probe_id} prompt is required")
    return probes


def evaluate_probe(probe: Probe, content: str) -> ProbeEvaluation:
    normalized = content.strip()
    if probe.validator == "none":
        return ProbeEvaluation(True, 0.5, "该探针用于采集行为特征，不做硬性对错判断。")
    if probe.validator == "contains":
        expected = str(probe.expected)
        passed = expected in normalized
        return ProbeEvaluation(passed, 1.0 if passed else 0.0, f"期望输出包含 {expected!r}。")
    if probe.validator == "contains_all":
        expected_items = [str(item) for item in probe.expected]
        missing = [item for item in expected_items if item not in normalized]
        passed = not missing
        reason = "所有关键片段均出现。" if passed else f"缺少关键片段：{', '.join(missing)}。"
        return ProbeEvaluation(passed, 1.0 if passed else 0.0, reason)
    if probe.validator == "json_value":
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return ProbeEvaluation(False, 0.0, "输出不是合法 JSON。")
        passed = parsed == probe.expected
        return ProbeEvaluation(passed, 1.0 if passed else 0.25, "检查严格 JSON 是否匹配期望对象。")
    raise ValueError(f"unknown validator: {probe.validator}")
