"""Request builder for Freebuff2API (OpenAI-compatible chat completions).

Freebuff2API is a Go proxy to codebuff.com that exposes OpenAI-compatible
/chat/completions and /v1/messages endpoints.  It accepts standard OpenAI
request bodies with ``model``, ``messages``, ``stream``, ``tools``, etc.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.anthropic import ReasoningReplayMode, build_base_request_body
from core.anthropic.conversion import OpenAIConversionError
from providers.exceptions import InvalidRequestError


def _apply_highest_reasoning(
    extra_body: dict[str, Any], max_tokens: int | None
) -> None:
    """Set the strongest reasoning hints accepted by the Freebuff proxy."""
    extra_body["reasoning_effort"] = "max"
    # Note: include_reasoning and chat_template_kwargs are vLLM-specific
    # and not supported by Freebuff's upstream (codebuff.com).
    # Only send the standard reasoning_effort field.


def build_request_body(request_data: Any, *, thinking_enabled: bool) -> dict:
    """Build OpenAI-format request body from an Anthropic request for Freebuff."""
    logger.debug(
        "FREEBUFF_REQUEST: conversion start model={} msgs={}",
        getattr(request_data, "model", "?"),
        len(getattr(request_data, "messages", [])),
    )
    try:
        body = build_base_request_body(
            request_data,
            reasoning_replay=ReasoningReplayMode.REASONING_CONTENT
            if thinking_enabled
            else ReasoningReplayMode.DISABLED,
        )
    except OpenAIConversionError as exc:
        raise InvalidRequestError(str(exc)) from exc

    # Pass through extra_body if present (user-supplied provider hints).
    extra_body: dict[str, Any] = {}
    request_extra = getattr(request_data, "extra_body", None)
    if isinstance(request_extra, dict) and request_extra:
        extra_body.update(request_extra)
    if thinking_enabled:
        _apply_highest_reasoning(extra_body, body.get("max_tokens"))
    if extra_body:
        body["extra_body"] = extra_body

    logger.debug(
        "FREEBUFF_REQUEST: conversion done model={} msgs={} tools={}",
        body.get("model"),
        len(body.get("messages", [])),
        len(body.get("tools", [])),
    )
    return body
