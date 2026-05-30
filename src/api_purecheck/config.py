from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


VALID_LEVELS = {"quick", "standard", "deep"}
VALID_FORMATS = {"text", "json", "html", "markdown", "md"}
VALID_API_TYPES = {"openai-compatible", "anthropic"}


@dataclass(frozen=True)
class AuditConfig:
    base_url: str
    api_key: str
    claimed_model: str
    level: str = "standard"
    output_format: str = "text"
    timeout_seconds: float = 60.0
    baseline_dir: str = "baselines"
    api_type: str = "openai-compatible"
    probe_file: str = ""

    def validate(self) -> None:
        if not self.base_url:
            raise ValueError("base_url is required")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must start with http:// or https://")
        if not self.api_key:
            raise ValueError("api_key is required")
        if not self.claimed_model:
            raise ValueError("claimed_model is required")
        if self.level not in VALID_LEVELS:
            raise ValueError(f"level must be one of: {', '.join(sorted(VALID_LEVELS))}")
        if self.output_format not in VALID_FORMATS:
            raise ValueError(f"format must be one of: {', '.join(sorted(VALID_FORMATS))}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if self.api_type not in VALID_API_TYPES:
            raise ValueError(f"api_type must be one of: {', '.join(sorted(VALID_API_TYPES))}")

    def redacted(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "api_key": redact_secret(self.api_key),
            "claimed_model": self.claimed_model,
            "level": self.level,
            "format": self.output_format,
            "timeout_seconds": self.timeout_seconds,
            "baseline_dir": self.baseline_dir,
            "api_type": self.api_type,
            "probe_file": self.probe_file,
        }


def redact_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"


def load_config(path: str | Path) -> AuditConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AuditConfig(
        base_url=str(data.get("base_url", "")),
        api_key=str(data.get("api_key", "")),
        claimed_model=str(data.get("claimed_model") or data.get("model") or ""),
        level=str(data.get("level", "standard")),
        output_format=str(data.get("format", "text")),
        timeout_seconds=float(data.get("timeout_seconds", 60.0)),
        baseline_dir=str(data.get("baseline_dir", "baselines")),
        api_type=str(data.get("api_type", "openai-compatible")),
        probe_file=str(data.get("probe_file", "")),
    )


def normalize_base_url(base_url: str, api_type: str) -> str:
    normalized = base_url.strip().rstrip("/")
    suffixes = (
        ("/chat/completions", "openai-compatible"),
        ("/messages", "anthropic"),
    )
    for suffix, suffix_api_type in suffixes:
        if api_type == suffix_api_type and normalized.endswith(suffix):
            return normalized[: -len(suffix)].rstrip("/")
    return normalized


def base_url_warnings(base_url: str, api_type: str) -> list[str]:
    normalized = base_url.strip().rstrip("/")
    warnings = []
    if api_type == "openai-compatible" and normalized.endswith("/chat/completions"):
        warnings.append("检测到你填入的是完整 /chat/completions 地址，工具会自动改用其 base URL。")
    if api_type == "anthropic" and normalized.endswith("/messages"):
        warnings.append("检测到你填入的是完整 /messages 地址，工具会自动改用其 base URL。")
    return warnings
