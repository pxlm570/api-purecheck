from __future__ import annotations

from api_purecheck.adapters.anthropic import AnthropicClient
from api_purecheck.adapters.openai_compatible import OpenAICompatibleClient
from api_purecheck.config import AuditConfig, normalize_base_url


def make_client(config: AuditConfig, timeout_seconds: float) -> OpenAICompatibleClient | AnthropicClient:
    if config.api_type == "anthropic":
        return AnthropicClient(
            base_url=normalize_base_url(config.base_url, config.api_type),
            api_key=config.api_key,
            timeout_seconds=timeout_seconds,
        )
    return OpenAICompatibleClient(
        base_url=normalize_base_url(config.base_url, config.api_type),
        api_key=config.api_key,
        timeout_seconds=timeout_seconds,
    )
