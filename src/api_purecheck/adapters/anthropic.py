from __future__ import annotations

from http.client import IncompleteRead
import json
from typing import Any
from urllib import error, request

from api_purecheck.adapters.openai_compatible import ApiRequestError, ChatCompletionResult, StreamCheckResult, open_url


class AnthropicClient:
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
        system_parts = [item["content"] for item in messages if item.get("role") == "system"]
        user_messages = [
            {"role": "user" if item.get("role") == "system" else item.get("role", "user"), "content": item.get("content", "")}
            for item in messages
            if item.get("role") != "system"
        ]
        payload: dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)
        response = self._post_json_with_fallback(payload)
        return parse_anthropic_message(response)

    def create_stream_check(self, *, model: str) -> StreamCheckResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "请只输出 PURECHECK_STREAM_OK，不要添加任何其他内容。"}],
            "system": "你正在接受一个轻量 API 流式响应检测。请严格按用户要求回答。",
            "temperature": 0.0,
            "max_tokens": 32,
            "stream": True,
        }
        errors = []
        for path in self._message_paths():
            try:
                return self._post_stream(path, payload)
            except ApiRequestError as exc:
                errors.append(exc)
                if not _should_try_next_path(exc):
                    raise
        if errors:
            raise errors[-1]
        raise ApiRequestError("no Anthropic stream path candidates")

    def _post_json_with_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        errors = []
        for path in self._message_paths():
            try:
                return self._post_json(path, payload)
            except ApiRequestError as exc:
                errors.append(exc)
                if not _should_try_next_path(exc):
                    raise
        if errors:
            raise errors[-1]
        raise ApiRequestError("no Anthropic message path candidates")

    def _message_paths(self) -> list[str]:
        lower = self.base_url.lower()
        if lower.endswith("/v1"):
            return ["/messages"]
        if lower.endswith("/anthropic"):
            return ["/messages", "/v1/messages"]
        return ["/v1/messages", "/messages"]

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
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

    def _post_stream(self, path: str, payload: dict[str, Any]) -> StreamCheckResult:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "api-purecheck/0.1",
            },
            method="POST",
        )
        try:
            with open_url(req, timeout=self.timeout_seconds) as resp:
                content_type = resp.headers.get("Content-Type", "")
                return parse_anthropic_sse(resp, content_type)
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


def parse_anthropic_message(data: dict[str, Any]) -> ChatCompletionResult:
    content_blocks = data.get("content", [])
    text_parts = []
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return ChatCompletionResult(
        model=str(data.get("model", "")),
        content="".join(text_parts),
        finish_reason=str(data.get("stop_reason", "")),
        usage=usage,
        raw_keys=sorted(str(key) for key in data.keys()),
    )


def parse_anthropic_sse(lines: Any, content_type: str) -> StreamCheckResult:
    event_count = 0
    done_seen = False
    finish_seen = False
    content_parts: list[str] = []
    raw_event_types: list[str] = []
    event_type_counts: dict[str, int] = {}
    current_event = ""

    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
            if current_event and current_event not in raw_event_types:
                raw_event_types.append(current_event)
            if current_event in {"message_stop", "done"}:
                done_seen = True
            continue
        if not line.startswith("data:"):
            continue
        event_count += 1
        data = line.removeprefix("data:").strip()
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, dict):
            continue
        event_type = str(chunk.get("type") or current_event)
        if event_type and event_type not in raw_event_types:
            raw_event_types.append(event_type)
        if event_type:
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        if event_type in {"message_stop", "done"}:
            done_seen = True
        if event_type == "message_delta" and chunk.get("delta"):
            finish_seen = True
        delta = chunk.get("delta", {})
        if isinstance(delta, dict):
            text = delta.get("text")
            if isinstance(text, str):
                content_parts.append(text)

    return StreamCheckResult(
        ok=bool(event_count),
        content="".join(content_parts),
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


def _should_try_next_path(exc: ApiRequestError) -> bool:
    if exc.status_code in {404, 405}:
        return True
    message = str(exc).lower()
    return "response is not valid json" in message and (
        "html" in message or "web page" in message or "text/html" in message
    )


def _invalid_json_message(content_type: str, text: str) -> str:
    preview = " ".join(text.strip().split())[:160]
    if not preview:
        preview = "<empty>"
    if "<html" in preview.lower() or "<!doctype" in preview.lower() or "text/html" in content_type.lower():
        return f"response is not valid JSON; server returned HTML or a web page; content_type={content_type}; preview={preview}"
    return f"response is not valid JSON; content_type={content_type}; preview={preview}"
