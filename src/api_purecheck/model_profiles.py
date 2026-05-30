from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    family: str
    display_name: str
    providers: tuple[str, ...]
    api_types: tuple[str, ...]
    model_names: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ModelProfileMatch:
    model: str
    family: str
    display_name: str
    match_type: str
    confidence: str


MODEL_PROFILES = [
    ModelProfile(
        family="gpt",
        display_name="OpenAI GPT",
        providers=("OpenAI", "Azure OpenAI", "中转站"),
        api_types=("openai-compatible",),
        model_names=("gpt-5.2", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"),
        notes="GPT 模型通常使用 OpenAI-compatible 协议；中转站可能使用别名或旧模型名。",
    ),
    ModelProfile(
        family="claude",
        display_name="Anthropic Claude",
        providers=("Anthropic", "Claude", "中转站"),
        api_types=("anthropic", "openai-compatible"),
        model_names=(
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
        ),
        notes="Claude 可使用 Anthropic Messages API，也常被中转站包装成 OpenAI-compatible。",
    ),
    ModelProfile(
        family="deepseek",
        display_name="DeepSeek",
        providers=("DeepSeek", "中转站"),
        api_types=("openai-compatible", "anthropic"),
        model_names=("deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", "deepseek-v4-flash"),
        notes="DeepSeek 官方和中转站模型名可能不同；遇到 400 时优先查看错误信息中的 suggested_models。",
    ),
    ModelProfile(
        family="kimi",
        display_name="Moonshot / Kimi",
        providers=("Moonshot", "Kimi", "中转站"),
        api_types=("openai-compatible",),
        model_names=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2", "kimi-k2-0905"),
        notes="Moonshot/Kimi 常见为 OpenAI-compatible。不同中转站可能使用 kimi-* 或 moonshot-* 命名。",
    ),
    ModelProfile(
        family="glm",
        display_name="GLM / 智谱",
        providers=("智谱", "Zhipu", "中转站"),
        api_types=("openai-compatible",),
        model_names=("glm-4", "glm-4-plus", "glm-4-air", "glm-4-flash", "glm-4.5", "glm-4.5-air"),
        notes="智谱 GLM 在不同平台常见 glm-4、glm-4-air、glm-4-flash 等命名。",
    ),
    ModelProfile(
        family="minimax",
        display_name="MiniMax",
        providers=("MiniMax", "中转站"),
        api_types=("openai-compatible",),
        model_names=("abab6.5s-chat", "abab6.5g-chat", "abab6.5t-chat", "MiniMax-Text-01"),
        notes="MiniMax 模型名差异较大；优先以中转站文档中的精确 model 为准。",
    ),
]


FAMILY_PREFIXES = {
    "gpt": ("gpt-", "o1", "o3", "o4"),
    "claude": ("claude-",),
    "deepseek": ("deepseek-",),
    "kimi": ("kimi-", "moonshot-"),
    "glm": ("glm-",),
    "minimax": ("minimax-", "abab"),
}


def profile_families() -> list[str]:
    return [profile.family for profile in MODEL_PROFILES]


def get_profile(family: str) -> ModelProfile | None:
    normalized = family.strip().lower()
    for profile in MODEL_PROFILES:
        if profile.family == normalized:
            return profile
    return None


def all_model_names() -> list[str]:
    names: list[str] = []
    for profile in MODEL_PROFILES:
        for model_name in profile.model_names:
            if model_name not in names:
                names.append(model_name)
    return names


def match_model_profile(model_name: str) -> ModelProfileMatch | None:
    normalized = _normalize_model_name(model_name)
    if not normalized:
        return None

    for profile in MODEL_PROFILES:
        for known_name in profile.model_names:
            if normalized == _normalize_model_name(known_name):
                return ModelProfileMatch(
                    model=model_name,
                    family=profile.family,
                    display_name=profile.display_name,
                    match_type="exact",
                    confidence="high",
                )

    for profile in MODEL_PROFILES:
        prefixes = FAMILY_PREFIXES.get(profile.family, ())
        if any(normalized.startswith(prefix) for prefix in prefixes):
            return ModelProfileMatch(
                model=model_name,
                family=profile.family,
                display_name=profile.display_name,
                match_type="prefix",
                confidence="medium",
            )

    return None


def profile_match_to_dict(match: ModelProfileMatch | None) -> dict[str, str]:
    if match is None:
        return {
            "model": "",
            "family": "unknown",
            "display_name": "unknown",
            "match_type": "none",
            "confidence": "none",
        }
    return {
        "model": match.model,
        "family": match.family,
        "display_name": match.display_name,
        "match_type": match.match_type,
        "confidence": match.confidence,
    }


def _normalize_model_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")
