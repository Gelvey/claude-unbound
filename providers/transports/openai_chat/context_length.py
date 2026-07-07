"""Clamp ``max_tokens`` after OpenAI-style context-length 400 errors.

Some upstreams (e.g. Cloudflare Workers AI) enforce
``input_tokens + max_tokens <= context_window`` and reject the request with a
400 instead of truncating output. Clients like Claude Code send a large fixed
``max_tokens`` (e.g. 32000), so every request to a small-context model fails
outright. The error message reports the model's context limit and the counted
input tokens, which is enough to compute a safe retry value:

    This model's maximum context length is 32768 tokens. However, you
    requested 32000 output tokens and your prompt contains at least 769 input
    tokens, for a total of at least 32769 tokens. Please reduce the length of
    the input prompt or the number of requested output tokens.

The helpers here are provider-neutral; providers opt in via their
``_get_retry_request_body`` hook.
"""

from __future__ import annotations

import json
import re

import openai

# Safety margin against off-by-a-few token counting differences upstream.
CONTEXT_CLAMP_MARGIN_TOKENS = 64

# Below this the response would be uselessly truncated; surface the real error.
_MIN_CLAMPED_MAX_TOKENS = 128

_CONTEXT_LIMIT_RE = re.compile(
    r"maximum context length is\s+(\d+)\s+tokens", re.IGNORECASE
)
# Cloudflare AiError (HTTP 413): "estimated number of input and maximum output
# tokens (56789) exceeded this model context window limit (24000)". Only the
# input+max_tokens total is reported, so recovering the input count requires
# the request's current ``max_tokens``.
_AI_ERROR_TOTAL_RE = re.compile(
    r"estimated number of input and maximum output tokens\s+\((\d+)\)\s+"
    r"exceeded this model context window limit\s+\((\d+)\)",
    re.IGNORECASE,
)
_INPUT_TOKENS_RES = (
    # Cloudflare / vLLM: "your prompt contains at least 769 input tokens"
    re.compile(r"(?:at least\s+)?(\d+)\s+input tokens", re.IGNORECASE),
    # OpenAI classic: "you requested 33224 tokens (1224 in the messages, ...)"
    re.compile(r"(\d+)\s+(?:tokens\s+)?in the messages", re.IGNORECASE),
)


def openai_error_text(error: Exception) -> str:
    """Combine ``str(error)`` with the structured error body when present."""
    text = str(error)
    body = getattr(error, "body", None)
    if body is not None:
        text = f"{text} {json.dumps(body, default=str)}"
    return text


def _extract_input_tokens(error_text: str) -> int | None:
    for pattern in _INPUT_TOKENS_RES:
        match = pattern.search(error_text)
        if match is not None:
            return int(match.group(1))
    return None


def clamped_max_tokens_from_context_length_error(
    error_text: str, current_max_tokens: object
) -> int | None:
    """Return a reduced ``max_tokens`` parsed from a context-length error.

    Returns ``None`` when the message is not a parsable context-length error,
    when the prompt alone already (nearly) fills the context window, or when
    the computed value would not actually lower the current ``max_tokens``.
    """
    limit_and_input = _extract_limit_and_input_tokens(error_text, current_max_tokens)
    if limit_and_input is None:
        return None
    limit_tokens, input_tokens = limit_and_input

    clamped = limit_tokens - input_tokens - CONTEXT_CLAMP_MARGIN_TOKENS
    if clamped < _MIN_CLAMPED_MAX_TOKENS:
        return None
    if isinstance(current_max_tokens, int) and clamped >= current_max_tokens:
        return None
    return clamped


def _extract_limit_and_input_tokens(
    error_text: str, current_max_tokens: object
) -> tuple[int, int] | None:
    """Return ``(context_limit, input_tokens)`` parsed from a context error."""
    limit_match = _CONTEXT_LIMIT_RE.search(error_text)
    if limit_match is not None:
        input_tokens = _extract_input_tokens(error_text)
        if input_tokens is None:
            return None
        return int(limit_match.group(1)), input_tokens

    ai_error_match = _AI_ERROR_TOTAL_RE.search(error_text)
    if ai_error_match is None:
        return None
    # The AiError total is input + max_tokens; recovering the input count
    # requires the request's current integer ``max_tokens``.
    if not isinstance(current_max_tokens, int):
        return None
    total_tokens = int(ai_error_match.group(1))
    limit_tokens = int(ai_error_match.group(2))
    return limit_tokens, total_tokens - current_max_tokens


def context_length_clamped_retry_body(error: Exception, body: dict) -> dict | None:
    """Return a shallow copy of ``body`` with clamped ``max_tokens``, or ``None``."""
    # 400: vLLM/OpenAI-style context-length errors.
    # 413: Cloudflare AiError context-window rejections (openai.APIStatusError).
    if not isinstance(error, openai.BadRequestError) and getattr(
        error, "status_code", None
    ) not in (400, 413):
        return None
    clamped = clamped_max_tokens_from_context_length_error(
        openai_error_text(error), body.get("max_tokens")
    )
    if clamped is None:
        return None
    retry_body = dict(body)
    retry_body["max_tokens"] = clamped
    return retry_body
