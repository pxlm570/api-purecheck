from __future__ import annotations

from dataclasses import dataclass, field
from http.client import IncompleteRead
import json
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


class ApiRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ChatCompletionResult:
    model: str
    content: str
    finish_reason: str
    usage: dict[str, Any]
    raw_keys: list[str]


@dataclass(frozen=True)
class StreamCheckResult:
    ok: bool
    content: str
    event_count: int
    done_seen: bool
    finish_seen: bool
    content_type: str
    raw_event_types: list[str]
    event_type_counts: dict[str, int] = field(default_factory=dict)
    error: str = ""


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> ChatCompletionResult:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = self._post_json("/chat/completions", payload)
        return parse_chat_completion(response)

    def create_stream_check(self, *, model: str) -> StreamCheckResult:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你正在接受一个轻量 API 流式响应检测。请严格按用户要求回答。",
                },
                {"role": "user", "content": "请只输出 PURECHECK_STREAM_OK，不要添加任何其他内容。"},
            ],
            "temperature": 0.0,
            "max_tokens": 32,
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "api-purecheck/0.1",
            },
            method="POST",
        )
        try:
            with open_url(req, timeout=self.timeout_seconds) as resp:
                content_type = resp.headers.get("Content-Type", "")
                return parse_openai_sse(resp, content_type)
        except error.HTTPError as exc:
            detail = _safe_error_body(exc)
            raise ApiRequestError(f"HTTP {exc.code}: {detail}", exc.code) from exc
        except error.URLError as exc:
            raise ApiRequestError(f"request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ApiRequestError("request timed out") from exc
        except IncompleteRead as exc:
            raise ApiRequestError("response was incomplete; server closed the connection early") from exc
        except OSError as exc:
            raise ApiRequestError(f"request failed: {exc}") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "api-purecheck/0.1",
            },
            method="POST",
        )
        try:
            with open_url(req, timeout=self.timeout_seconds) as resp:
                content_type = resp.headers.get("Content-Type", "")
                text = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = _safe_error_body(exc)
            raise ApiRequestError(f"HTTP {exc.code}: {detail}", exc.code) from exc
        except error.URLError as exc:
            raise ApiRequestError(f"request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ApiRequestError("request timed out") from exc
        except IncompleteRead as exc:
            raise ApiRequestError("response was incomplete; server closed the connection early") from exc
        except OSError as exc:
            raise ApiRequestError(f"request failed: {exc}") from exc

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ApiRequestError(_invalid_json_message(content_type, text)) from exc
        if not isinstance(parsed, dict):
            raise ApiRequestError("response JSON must be an object")
        return parsed


def parse_chat_completion(data: dict[str, Any]) -> ChatCompletionResult:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ApiRequestError("response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ApiRequestError("response choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ApiRequestError("response choice missing message")
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if content is None:
        content = ""
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return ChatCompletionResult(
        model=str(data.get("model", "")),
        content=str(content),
        finish_reason=str(first.get("finish_reason", "")),
        usage=usage,
        raw_keys=sorted(str(key) for key in data.keys()),
    )


def parse_openai_sse(lines: Any, content_type: str) -> StreamCheckResult:
    event_count = 0
    done_seen = False
    finish_seen = False
    content_parts: list[str] = []
    raw_event_types: list[str] = []
    event_type_counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
            if event_name and event_name not in raw_event_types:
                raw_event_types.append(event_name)
            if event_name:
                event_type_counts[event_name] = event_type_counts.get(event_name, 0) + 1
            continue
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        event_count += 1
        if data == "[DONE]":
            done_seen = True
            event_type_counts["[DONE]"] = event_type_counts.get("[DONE]", 0) + 1
            break
        event_type_counts["data"] = event_type_counts.get("data", 0) + 1
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, dict):
            continue
        choices = chunk.get("choices", [])
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                finish_seen = True
            delta = choice.get("delta", {})
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    content_parts.append(content)

    content = "".join(content_parts)
    return StreamCheckResult(
        ok=bool(event_count),
        content=content,
        event_count=event_count,
        done_seen=done_seen,
        finish_seen=finish_seen,
        content_type=content_type,
        raw_event_types=raw_event_types,
        event_type_counts=event_type_counts,
    )


def _safe_error_body(exc: error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        return exc.reason
    finally:
        exc.close()
    return body[:500] if body else exc.reason


def open_url(req: request.Request, *, timeout: float) -> Any:
    if _is_local_url(req.full_url):
        opener = request.build_opener(request.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return request.urlopen(req, timeout=timeout)


def _is_local_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _invalid_json_message(content_type: str, text: str) -> str:
    preview = " ".join(text.strip().split())[:160]
    if not preview:
        preview = "<empty>"
    if "<html" in preview.lower() or "<!doctype" in preview.lower() or "text/html" in content_type.lower():
        return f"response is not valid JSON; server returned HTML or a web page; content_type={content_type}; preview={preview}"
    return f"response is not valid JSON; content_type={content_type}; preview={preview}"
