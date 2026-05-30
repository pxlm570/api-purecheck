from __future__ import annotations

from dataclasses import dataclass

from api_purecheck.model_profiles import MODEL_PROFILES


@dataclass(frozen=True)
class ModelExample:
    provider: str
    model: str
    note: str


MODEL_EXAMPLES = [
    ModelExample("openai", "gpt-5.2", "OpenAI frontier model example"),
    ModelExample("openai", "gpt-5-mini", "OpenAI cost-efficient GPT-5 family example"),
    ModelExample("openai", "gpt-5-nano", "OpenAI low-cost GPT-5 family example"),
    ModelExample("openai", "gpt-4.1", "OpenAI non-reasoning GPT example"),
    ModelExample("openai", "gpt-4.1-mini", "OpenAI smaller GPT-4.1 example"),
    ModelExample("openai", "gpt-4o", "OpenAI GPT-4o example"),
    ModelExample("openai", "gpt-4o-mini", "OpenAI smaller GPT-4o example"),
    ModelExample("anthropic", "claude-opus-4-1-20250805", "Anthropic Claude Opus 4.1 example"),
    ModelExample("anthropic", "claude-opus-4-20250514", "Anthropic Claude Opus 4 example"),
    ModelExample("anthropic", "claude-sonnet-4-20250514", "Anthropic Claude Sonnet 4 example"),
    ModelExample("anthropic", "claude-3-7-sonnet-20250219", "Anthropic Claude Sonnet 3.7 example"),
    ModelExample("anthropic", "claude-3-5-haiku-20241022", "Anthropic Claude Haiku 3.5 example"),
    ModelExample("anthropic", "claude-3-haiku-20240307", "Anthropic Claude Haiku 3 example"),
]

for profile in MODEL_PROFILES:
    for model_name in profile.model_names:
        MODEL_EXAMPLES.append(ModelExample(profile.family, model_name, f"{profile.display_name} model name example"))


def model_examples(provider: str | None = None) -> list[ModelExample]:
    if not provider:
        return list(MODEL_EXAMPLES)
    normalized = provider.strip().lower()
    return [item for item in MODEL_EXAMPLES if item.provider == normalized]
