"""Request builder for Cloudflare Workers AI (OpenAI-compatible chat completions).

The OpenAI-compat layer at ``/ai/v1/chat/completions`` accepts the same body
shape as OpenAI's chat completions endpoint, so we only need to skip Anthropic
``extra_body`` ingestion (the Cloudflare backend doesn't understand it) and
preserve caller ``extra_body`` for forward compatibility.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.anthropic import ReasoningReplayMode, build_base_request_body
from core.anthropic.conversion import OpenAIConversionError
from core.anthropic.session_key import stable_session_key
from providers.exceptions import InvalidRequestError

# Cloudflare routes requests with the same session-affinity key to the machine
# holding the conversation's prefix cache (better TTFT, more discounted cached
# tokens). See https://developers.cloudflare.com/workers-ai/.
SESSION_AFFINITY_HEADER = "x-session-affinity"


def build_request_body(request_data: Any, *, thinking_enabled: bool) -> dict:
    """Build OpenAI-format request body from an Anthropic request for Cloudflare AI."""
    logger.debug(
        "CLOUDFLARE_AI_REQUEST: conversion start model={} msgs={}",
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

    request_extra = getattr(request_data, "extra_body", None)
    if isinstance(request_extra, dict) and request_extra:
        body["extra_body"] = dict(request_extra)

    session_key = stable_session_key(request_data)
    if session_key:
        # Passed through to AsyncOpenAI ``create(**body)`` as request headers.
        body["extra_headers"] = {SESSION_AFFINITY_HEADER: session_key}

    logger.debug(
        "CLOUDFLARE_AI_REQUEST: conversion done model={} msgs={} tools={}",
        body.get("model"),
        len(body.get("messages", [])),
        len(body.get("tools", [])),
    )
    return body
