"""Context-length 400 parsing and max_tokens clamp retry."""

from __future__ import annotations

import openai
from httpx import HTTPStatusError, Request, Response

from providers.error_mapping import attach_provider_error_body
from providers.transports.openai_chat.context_length import (
    CONTEXT_CLAMP_MARGIN_TOKENS,
    clamped_max_tokens_from_context_length_error,
    context_length_clamped_retry_body,
    openai_error_text,
)

_CLOUDFLARE_400 = (
    "This model's maximum context length is 32768 tokens. However, you "
    "requested 32000 output tokens and your prompt contains at least 769 "
    "input tokens, for a total of at least 32769 tokens. Please reduce the "
    "length of the input prompt or the number of requested output tokens. "
    "(parameter=input_tokens, value=769)"
)

_OPENAI_CLASSIC_400 = (
    "This model's maximum context length is 8192 tokens. However, you "
    "requested 9224 tokens (1224 in the messages, 8000 in the completion). "
    "Please reduce the length of the messages or completion."
)

# Cloudflare rejects oversized requests with an HTTP 413 AiError reporting only
# the input+max_tokens total and the context window limit.
_CLOUDFLARE_413_AI_ERROR = (
    "3010: AiError: The estimated number of input and maximum output tokens "
    "(35000) exceeded this model context window limit (24000)"
)

# New Cloudflare shape (Workers AI): "maximum context length of N tokens" + a
# total-requested line. Input is reported directly as "X tokens from the input
# messages".
_CLOUDFLARE_NEW_400 = (
    "Requested token count exceeds the model's maximum context length of "
    "256000 tokens. You requested a total of 256800 tokens: 224800 tokens "
    "from the input messages and 32000 tokens for the completion."
)

# OpenRouter: "maximum context length is N tokens" (matched by the limit regex)
# but the input count is only recoverable from the "you requested about N tokens"
# total — 212745 total - 32000 output = 180745 input.
_OPENROUTER_400 = (
    "This endpoint's maximum context length is 131072 tokens. However, you "
    "requested about 212745 tokens (122163 of text input, 58582 of tool "
    "input, 32000 in the output). Please reduce the length of either one, "
    "or use the context-compression plugin to compress your prompt "
    "automatically."
)


def _bad_request(message: str) -> openai.BadRequestError:
    response = Response(status_code=400, request=Request("POST", "http://test"))
    return openai.BadRequestError(
        message, response=response, body={"error": {"message": message}}
    )


def _status_error(message: str, status_code: int) -> openai.APIStatusError:
    response = Response(status_code=status_code, request=Request("POST", "http://test"))
    return openai.APIStatusError(
        message, response=response, body={"error": {"message": message}}
    )


def _httpx_status_error(message: str, status_code: int) -> HTTPStatusError:
    """An httpx error with the body attached the way the Anthropic transport does."""
    response = Response(
        status_code=status_code,
        request=Request("POST", "http://test"),
        content=message.encode("utf-8"),
    )
    error = HTTPStatusError(message, request=response.request, response=response)
    attach_provider_error_body(error, message.encode("utf-8"))
    return error


def test_parses_cloudflare_input_tokens_shape() -> None:
    clamped = clamped_max_tokens_from_context_length_error(_CLOUDFLARE_400, 32000)
    assert clamped == 32768 - 769 - CONTEXT_CLAMP_MARGIN_TOKENS


def test_parses_openai_in_the_messages_shape() -> None:
    clamped = clamped_max_tokens_from_context_length_error(_OPENAI_CLASSIC_400, 8000)
    assert clamped == 8192 - 1224 - CONTEXT_CLAMP_MARGIN_TOKENS


def test_returns_none_for_unrelated_error_text() -> None:
    assert (
        clamped_max_tokens_from_context_length_error("invalid tool schema", 32000)
        is None
    )


def test_returns_none_when_prompt_alone_fills_context() -> None:
    text = (
        "This model's maximum context length is 131072 tokens. However, you "
        "requested 16000 output tokens and your prompt contains at least "
        "131000 input tokens."
    )
    assert clamped_max_tokens_from_context_length_error(text, 16000) is None


def test_returns_none_when_clamp_would_not_lower_max_tokens() -> None:
    # Clamped value >= current max_tokens must not retry (avoids retry loops).
    assert clamped_max_tokens_from_context_length_error(_CLOUDFLARE_400, 100) is None


def test_parses_cloudflare_413_ai_error_shape() -> None:
    # input = 35000 total - 32000 max_tokens = 3000
    clamped = clamped_max_tokens_from_context_length_error(
        _CLOUDFLARE_413_AI_ERROR, 32000
    )
    assert clamped == 24000 - 3000 - CONTEXT_CLAMP_MARGIN_TOKENS


def test_ai_error_returns_none_when_input_alone_fills_context() -> None:
    text = (
        "AiError: The estimated number of input and maximum output tokens "
        "(56000) exceeded this model context window limit (24000)"
    )
    # input = 56000 - 32000 = 24000 fills the whole window -> unfixable.
    assert clamped_max_tokens_from_context_length_error(text, 32000) is None


def test_ai_error_requires_integer_current_max_tokens() -> None:
    # The AiError total is input + max_tokens; without an int max_tokens the
    # input count cannot be recovered.
    assert (
        clamped_max_tokens_from_context_length_error(_CLOUDFLARE_413_AI_ERROR, None)
        is None
    )
    assert (
        clamped_max_tokens_from_context_length_error(_CLOUDFLARE_413_AI_ERROR, "32000")
        is None
    )


def test_retry_body_accepts_413_ai_error() -> None:
    body = {"model": "m", "max_tokens": 32000, "messages": []}
    retry = context_length_clamped_retry_body(
        _status_error(_CLOUDFLARE_413_AI_ERROR, 413), body
    )
    assert retry is not None
    assert retry["max_tokens"] == 24000 - 3000 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert body["max_tokens"] == 32000  # original untouched


def test_retry_body_rejects_other_status_codes() -> None:
    body = {"model": "m", "max_tokens": 32000}
    assert (
        context_length_clamped_retry_body(
            _status_error(_CLOUDFLARE_413_AI_ERROR, 500), body
        )
        is None
    )


def test_retry_body_clamps_max_tokens_and_copies_body() -> None:
    body = {"model": "m", "max_tokens": 32000, "messages": []}
    retry = context_length_clamped_retry_body(_bad_request(_CLOUDFLARE_400), body)
    assert retry is not None
    assert retry["max_tokens"] == 32768 - 769 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert retry is not body
    assert body["max_tokens"] == 32000  # original untouched


def test_retry_body_requires_400_status() -> None:
    body = {"model": "m", "max_tokens": 32000}
    assert (
        context_length_clamped_retry_body(RuntimeError(_CLOUDFLARE_400), body) is None
    )


def test_retry_body_reads_message_from_error_body() -> None:
    # Message only present in the structured body, not str(error).
    response = Response(status_code=400, request=Request("POST", "http://test"))
    error = openai.BadRequestError(
        "bad request",
        response=response,
        body={"error": {"message": _CLOUDFLARE_400}},
    )
    retry = context_length_clamped_retry_body(error, {"max_tokens": 32000})
    assert retry is not None
    assert retry["max_tokens"] == 32768 - 769 - CONTEXT_CLAMP_MARGIN_TOKENS


def test_openai_error_text_includes_structured_body() -> None:
    text = openai_error_text(_bad_request("boom"))
    assert "boom" in text


def test_cloudflare_provider_retry_hook_clamps() -> None:
    from providers.base import ProviderConfig
    from providers.cloudflare_ai.client import CloudflareAiProvider

    provider = CloudflareAiProvider(
        ProviderConfig(api_key="k", base_url="http://localhost/ai/v1")
    )
    body = {"model": "m", "max_tokens": 32000, "messages": []}
    retry = provider._get_retry_request_body(_bad_request(_CLOUDFLARE_400), body)
    assert retry is not None
    assert retry["max_tokens"] == 32768 - 769 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert provider._get_retry_request_body(RuntimeError("nope"), body) is None


def test_parses_new_cloudflare_of_form_and_input_messages() -> None:
    # 256000 - 224800 - margin
    clamped = clamped_max_tokens_from_context_length_error(_CLOUDFLARE_NEW_400, 32000)
    assert clamped == 256000 - 224800 - CONTEXT_CLAMP_MARGIN_TOKENS


def test_parses_openrouter_total_requested_fallback() -> None:
    # input = 212745 total - 32000 output = 180745; 180745 > 131072 limit ->
    # prompt alone fills the window -> unfixable by clamping -> None.
    assert clamped_max_tokens_from_context_length_error(_OPENROUTER_400, 32000) is None


def test_openrouter_total_fallback_clamps_when_input_under_limit() -> None:
    # Borderline OpenRouter case: input (100000) is below the 131072 limit but
    # input + max_tokens (132000) exceeds it. total = 132000; clamp must lower
    # max_tokens, not raise it.
    text = (
        "This endpoint's maximum context length is 131072 tokens. However, you "
        "requested about 132000 tokens (100000 of text input, 32000 in the output)."
    )
    clamped = clamped_max_tokens_from_context_length_error(text, 32000)
    assert clamped == 131072 - 100000 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert clamped < 32000  # the clamp must actually lower max_tokens


def test_retry_body_clamps_new_cloudflare_httpx_error() -> None:
    body = {"model": "m", "max_tokens": 32000, "messages": []}
    retry = context_length_clamped_retry_body(
        _httpx_status_error(_CLOUDFLARE_NEW_400, 400), body
    )
    assert retry is not None
    assert retry["max_tokens"] == 256000 - 224800 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert body["max_tokens"] == 32000  # original untouched


def test_retry_body_rejects_httpx_500() -> None:
    body = {"model": "m", "max_tokens": 32000}
    assert (
        context_length_clamped_retry_body(
            _httpx_status_error(_CLOUDFLARE_NEW_400, 500), body
        )
        is None
    )


def test_openai_error_text_reads_fcc_provider_error_body_bytes() -> None:
    error = _httpx_status_error(_CLOUDFLARE_NEW_400, 400)
    text = openai_error_text(error)
    assert "maximum context length of 256000 tokens" in text


def test_openrouter_provider_retry_hook_clamps() -> None:
    from providers.base import ProviderConfig
    from providers.open_router.client import OpenRouterProvider

    provider = OpenRouterProvider(
        ProviderConfig(api_key="k", base_url="https://openrouter.ai/api/v1")
    )
    body = {"model": "m", "max_tokens": 32000, "messages": []}
    retry = provider._get_retry_request_body(
        _httpx_status_error(_CLOUDFLARE_NEW_400, 400), body
    )
    assert retry is not None
    assert retry["max_tokens"] == 256000 - 224800 - CONTEXT_CLAMP_MARGIN_TOKENS
    assert provider._get_retry_request_body(RuntimeError("nope"), body) is None
