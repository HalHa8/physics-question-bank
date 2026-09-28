import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

from mathbank.ai_http import (
    AIProviderHTTPError,
    AIStreamResponseError,
    collect_streamed_completion,
    is_stream_read_timeout,
    post_chat_completion,
    robust_request_get,
    robust_request_post,
)
from mathbank.ai_providers import resolve_text_provider


def test_post_chat_completion_builds_common_request():
    provider = resolve_text_provider(
        "ZHONGZHAN_GPT/gpt-5.6-sol",
        {
            "ZHONGZHAN_GPT_API_KEY": "secret-key",
            "ZHONGZHAN_GPT_BASE_URL": "https://transit.example/v1/",
        },
    )
    response = MagicMock(status_code=200)

    with patch(
        "mathbank.ai_http.robust_request_post", return_value=response
    ) as mock_post:
        result = post_chat_completion(
            provider,
            {"model": "gpt-5.6-sol", "messages": []},
            timeout=45,
        )

    assert result is response
    mock_post.assert_called_once_with(
        "https://transit.example/v1/chat/completions",
        headers={
            "Authorization": "Bearer secret-key",
            "Content-Type": "application/json",
        },
        json={"model": "gpt-5.6-sol", "messages": []},
        timeout=45,
    )


def test_post_chat_completion_raises_consistent_http_error():
    provider = resolve_text_provider(
        "DEEPSEEK/deepseek-chat",
        {"DEEPSEEK_API_KEY": "secret-key"},
    )
    response = MagicMock(
        status_code=429,
        text="sensitive prompt fragment",
        headers={"x-request-id": "req-safe-123"},
    )

    with patch("mathbank.ai_http.robust_request_post", return_value=response):
        with pytest.raises(AIProviderHTTPError) as exc_info:
            post_chat_completion(
                provider,
                {"model": "deepseek-chat"},
                timeout=30,
                provider_name="DeepSeek (DEEPSEEK_API_KEY)",
            )

    assert str(exc_info.value) == (
        "DeepSeek (DEEPSEEK_API_KEY) 接口错误: "
        "HTTP 429 (request_id=req-safe-123)"
    )
    assert "sensitive prompt fragment" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("request_helper", "request_target"),
    [
        (robust_request_post, "mathbank.ai_http.requests.post"),
        (robust_request_get, "mathbank.ai_http.requests.get"),
    ],
)
def test_domestic_provider_requests_bypass_proxies_immediately(
    request_helper, request_target
):
    response = MagicMock(status_code=200)

    with patch(request_target, return_value=response) as request_mock:
        result = request_helper("https://dashscope.aliyuncs.com/api", timeout=10)

    assert result is response
    request_mock.assert_called_once_with(
        "https://dashscope.aliyuncs.com/api",
        timeout=10,
        proxies={"http": None, "https": None},
    )


def test_external_request_retries_once_without_proxies_on_proxy_error():
    response = MagicMock(status_code=200)

    with patch(
        "mathbank.ai_http.requests.post",
        side_effect=[requests.exceptions.ProxyError("proxy failed"), response],
    ) as request_mock:
        result = robust_request_post("https://transit.example/v1", timeout=10)

    assert result is response
    assert request_mock.call_count == 2
    retry_kwargs = request_mock.call_args_list[1].kwargs
    assert retry_kwargs["proxies"] == {"http": None, "https": None}


def test_post_read_timeout_is_not_retried_to_avoid_duplicate_billing():
    with patch(
        "mathbank.ai_http.requests.post",
        side_effect=requests.exceptions.ReadTimeout("provider timed out"),
    ) as request_mock:
        with pytest.raises(requests.exceptions.ReadTimeout):
            robust_request_post("https://transit.example/v1", timeout=10)

    request_mock.assert_called_once()


@pytest.mark.parametrize("error", [requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout])
def test_explicit_single_attempt_skips_even_connection_retry(error):
    provider = resolve_text_provider("ZHONGZHAN_GPT/gpt-5.6-sol", {
        "ZHONGZHAN_GPT_API_KEY": "unused-test-key",
        "ZHONGZHAN_GPT_BASE_URL": "https://transit.example/v1/",
    })
    with patch("mathbank.ai_http.requests.post", side_effect=error("connect failure")) as post:
        with pytest.raises(error):
            post_chat_completion(provider, {"model": "test", "messages": []}, timeout=10,
                                 retry_connection=False)
    post.assert_called_once()
    assert "retry_connection" not in post.call_args.kwargs


def _sse_response(*events):
    closed = []
    response = SimpleNamespace(
        iter_lines=lambda: iter(events), close=lambda: closed.append(True),
    )
    return response, closed


def test_streamed_completion_collects_chunks_and_real_usage_only():
    first = {"choices": [{"delta": {"content": '{"markdown":"测'}, "finish_reason": None}]}
    second = {"choices": [{"delta": {"content": '试"}'}, "finish_reason": "stop"}]}
    usage = {"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 5}}
    response, closed = _sse_response(
        b': heartbeat',
        ("data: " + json.dumps(first, ensure_ascii=False)).encode(),
        ("data: " + json.dumps(second, ensure_ascii=False)).encode(),
        ("data: " + json.dumps(usage)).encode(),
        b'data: [DONE]',
    )
    body = collect_streamed_completion(response, max_content_chars=100, check_cancelled=lambda: None)
    assert body["choices"][0]["message"]["content"] == '{"markdown":"测试"}'
    assert body["usage"] == usage["usage"]
    assert closed == [True]


@pytest.mark.parametrize("events", [
    [b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"stop"}]}'],
    [b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}', b'data: [DONE]'],
    [b'data: {"error":"secret provider details"}', b'data: [DONE]'],
    [b'data: not-json secret provider details', b'data: [DONE]'],
])
def test_streamed_completion_rejects_partial_or_bad_events_without_leak(events):
    response, closed = _sse_response(*events)
    with pytest.raises(AIStreamResponseError) as caught:
        collect_streamed_completion(response, max_content_chars=100, check_cancelled=lambda: None)
    assert "secret" not in str(caught.value)
    assert closed == [True]


def test_streamed_completion_bounds_output_and_closes_on_cancel():
    event = b'data: {"choices":[{"delta":{"content":"12345"},"finish_reason":"stop"}]}'
    response, closed = _sse_response(event, b'data: [DONE]')
    with pytest.raises(AIStreamResponseError, match="过长"):
        collect_streamed_completion(response, max_content_chars=4, check_cancelled=lambda: None)
    assert closed == [True]

    response, closed = _sse_response(event)
    with pytest.raises(RuntimeError, match="cancelled"):
        collect_streamed_completion(response, max_content_chars=100,
                                    check_cancelled=lambda: (_ for _ in ()).throw(RuntimeError("cancelled")))
    assert closed == [True]


def test_streamed_body_read_timeout_wrapped_by_requests_is_identified():
    wrapped = requests.exceptions.ConnectionError(
        Urllib3ReadTimeoutError(None, "https://private.example", "timed out"))
    assert is_stream_read_timeout(wrapped)
    assert is_stream_read_timeout(requests.exceptions.ReadTimeout("timed out"))
    assert not is_stream_read_timeout(requests.exceptions.ConnectionError("connection broken"))
