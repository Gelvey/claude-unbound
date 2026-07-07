"""Context-length 400 parsing and max_tokens clamp retry."""

from __future__ import annotations

import openai
from httpx import Request, Response

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
