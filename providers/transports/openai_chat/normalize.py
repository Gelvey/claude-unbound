"""Shared OpenAI-chat request-body normalization helpers."""

from __future__ import annotations

from typing import Any


def normalize_max_completion_tokens(body: dict[str, Any]) -> None:
    """Prefer ``max_completion_tokens`` over the deprecated ``max_tokens``.

    When ``max_completion_tokens`` is already set, drop ``max_tokens``.
    Otherwise, when ``max_tokens`` is present and non-null, rename it. Used
    by OpenAI-compatible providers (Groq, Cerebras) whose APIs reject the
    deprecated field in favor of the renamed one.
    """
    if "max_completion_tokens" in body:
        body.pop("max_tokens", None)
        return
    if "max_tokens" in body and body["max_tokens"] is not None:
        body["max_completion_tokens"] = body.pop("max_tokens")
