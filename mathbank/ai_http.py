"""Shared HTTP transport helpers for AI provider requests."""

import json
import time
from typing import Any, Callable, Dict, Optional, Protocol

import requests
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError


class ChatProviderConfig(Protocol):
    provider_label: str
    api_key: Optional[str]
    credential_label: str
    chat_completions_url: Optional[str]


class AIProviderHTTPError(RuntimeError):
    """Raised when an AI provider returns a non-success HTTP response."""


class AIStreamResponseError(ValueError):
    """A streamed completion ended without one complete, bounded answer."""


def is_stream_read_timeout(exc: BaseException) -> bool:
    """requests wraps an idle streamed-body timeout in ConnectionError."""
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    return isinstance(exc, requests.exceptions.ConnectionError) and any(
        isinstance(arg, Urllib3ReadTimeoutError) for arg in exc.args
    )


def collect_streamed_completion(
    response, *, max_content_chars: int, check_cancelled: Callable[[], None],
    max_duration_seconds: float = 600,
) -> Dict[str, Any]:
    """Collect one OpenAI-compatible SSE answer without accepting partial output.

    Provider event bodies are intentionally never included in exceptions.
    """
    parts: list[str] = []
    content_chars = 0
    finish_reason = None
    done = False
    usage: dict = {}
    started = time.monotonic()
    try:
        for line in response.iter_lines():
            check_cancelled()
            if time.monotonic() - started > max_duration_seconds:
                raise AIStreamResponseError("流式识别超过总时限，未接受不完整结果。")
            if not line:
                continue
            if isinstance(line, bytes):
                try:
                    line = line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise AIStreamResponseError("流式识别返回了无效编码。") from exc
            if not isinstance(line, str) or len(line) > 1_000_000:
                raise AIStreamResponseError("流式识别事件过大或格式无效。")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                done = True
                break
            try:
                event = json.loads(data)
            except (TypeError, ValueError) as exc:
                raise AIStreamResponseError("流式识别事件不是有效 JSON。") from exc
            if not isinstance(event, dict) or "error" in event:
                raise AIStreamResponseError("识图服务返回了流式错误。")
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            choices = event.get("choices", [])
            if not isinstance(choices, list) or len(choices) > 1:
                raise AIStreamResponseError("流式识别候选格式无效。")
            if not choices:
                continue  # A final usage-only event is permitted.
            choice = choices[0]
            if not isinstance(choice, dict):
                raise AIStreamResponseError("流式识别候选格式无效。")
            reason = choice.get("finish_reason")
            if reason is not None:
                if finish_reason is not None and reason != finish_reason:
                    raise AIStreamResponseError("流式识别结束标记冲突。")
                finish_reason = reason
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                raise AIStreamResponseError("流式识别内容格式无效。")
            piece = delta.get("content")
            if piece is not None:
                if not isinstance(piece, str):
                    raise AIStreamResponseError("流式识别内容格式无效。")
                content_chars += len(piece)
                if content_chars > max_content_chars:
                    raise AIStreamResponseError("流式识别内容过长。")
                parts.append(piece)
        check_cancelled()
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    if not done or finish_reason != "stop" or not any(parts):
        raise AIStreamResponseError("流式识别未正常结束或输出被截断，未接受不完整结果。")
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": "".join(parts)}}],
        "usage": usage,
    }


def robust_request_post(url: str, *, retry_connection: bool = True, **kwargs):
    """POST with a conservative proxy fallback.

    A response/read failure may happen after the provider has already started
    and billed the request, so non-idempotent POSTs are only retried for an
    explicit proxy failure or a connection-establishment timeout.
    """

    is_domestic = any(
        domain in url.lower() for domain in ("aliyuncs.com", "siliconflow")
    )
    if is_domestic and "proxies" not in kwargs:
        kwargs["proxies"] = {"http": None, "https": None}

    try:
        return requests.post(url, **kwargs)
    except (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
    ) as exc:
        if not retry_connection or kwargs.get("proxies") == {"http": None, "https": None}:
            raise
        print(
            f"[Robust Network] Provider connection failed before a response "
            f"(type={type(exc).__name__}). Retrying once without proxies..."
        )
        retry_kwargs = kwargs.copy()
        retry_kwargs["proxies"] = {"http": None, "https": None}
        return requests.post(url, **retry_kwargs)


def robust_request_get(url: str, **kwargs):
    """GET with the project's existing proxy-bypass retry behavior."""

    is_domestic = any(
        domain in url.lower() for domain in ("aliyuncs.com", "siliconflow")
    )
    if is_domestic and "proxies" not in kwargs:
        kwargs["proxies"] = {"http": None, "https": None}

    try:
        return requests.get(url, **kwargs)
    except requests.exceptions.RequestException as exc:
        if kwargs.get("proxies") == {"http": None, "https": None}:
            raise
        print(
            f"[Robust Network] GET request to {url} failed: {str(exc)}. "
            "Retrying with proxies bypassed..."
        )
        retry_kwargs = kwargs.copy()
        retry_kwargs["proxies"] = {"http": None, "https": None}
        return requests.get(url, **retry_kwargs)


def build_bearer_headers(api_key: str) -> Dict[str, str]:
    """Build the common OpenAI-compatible authorization headers."""

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def post_chat_completion(
    provider: ChatProviderConfig,
    payload: Dict[str, Any],
    *,
    timeout: float | tuple[float, float],
    stream: bool = False,
    check_status: bool = True,
    provider_name: Optional[str] = None,
    retry_connection: bool = True,
):
    """Send one OpenAI-compatible chat completion request.

    Payload construction and response parsing remain the responsibility of the
    calling business flow.  Streaming callers can disable status checking so
    they can preserve their existing SSE error format.
    """

    if not provider.api_key:
        raise ValueError(f"未配置对应的 API Key ({provider.credential_label})")
    if not provider.chat_completions_url:
        raise ValueError(f"未配置对应的 API Base ({provider.provider_label})")

    request_kwargs = {
        "headers": build_bearer_headers(provider.api_key),
        "json": payload,
        "timeout": timeout,
    }
    if stream:
        request_kwargs["stream"] = True
    if not retry_connection:
        request_kwargs["retry_connection"] = False

    response = robust_request_post(
        provider.chat_completions_url,
        **request_kwargs,
    )
    if check_status and response.status_code != 200:
        display_name = provider_name or provider.provider_label
        # Provider bodies can echo prompt fragments or internal diagnostics.
        # Keep them out of browser-visible exceptions and logs; a request ID is
        # sufficient for support without exposing user content.
        request_id = ""
        headers = getattr(response, "headers", None)
        if headers:
            request_id = (
                headers.get("x-request-id")
                or headers.get("request-id")
                or headers.get("x-dashscope-request-id")
                or ""
            )
        suffix = f" (request_id={request_id})" if request_id else ""
        raise AIProviderHTTPError(
            f"{display_name} 接口错误: HTTP {response.status_code}{suffix}"
        )
    return response
