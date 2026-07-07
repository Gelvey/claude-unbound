"""Stable per-conversation keys for provider prompt-cache routing.

Providers with distributed prefix caches route requests by an opaque client
key: Cloudflare Workers AI honors an ``x-session-affinity`` header, and some
OpenAI-compatible providers accept a ``prompt_cache_key`` body field. Sending
the same key for every turn of a conversation lands repeat requests on the
machine holding the cached prefix, raising cache hit rates and cutting TTFT.

Key derivation prefers the client-supplied ``metadata.user_id`` (Claude Code
sends a stable per-session value) and falls back to hashing the system prompt
plus the first user message — both constant across turns of one conversation.
Keys are SHA-256 digests, so no conversation text leaves the gateway.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_KEY_HEX_CHARS = 32


def _stable_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        value = dump(exclude_none=True)
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError, ValueError:
        return str(value)


def _metadata_user_id(request_data: Any) -> str | None:
    metadata = getattr(request_data, "metadata", None)
    if isinstance(metadata, Mapping):
        user_id = metadata.get("user_id")
    else:
        user_id = getattr(metadata, "user_id", None)
    if isinstance(user_id, str) and user_id:
        return user_id
    return None


def _conversation_seed(request_data: Any) -> str | None:
    parts: list[str] = []
    system = getattr(request_data, "system", None)
    if system is not None:
        parts.append(_stable_text(system))
    for message in getattr(request_data, "messages", None) or []:
        if getattr(message, "role", None) == "user":
            parts.append(_stable_text(getattr(message, "content", "")))
            break
    joined = "\x00".join(part for part in parts if part)
    return joined or None


def stable_session_key(request_data: Any) -> str | None:
    """Return a stable opaque cache-routing key for this conversation, or None."""
    seed = _metadata_user_id(request_data) or _conversation_seed(request_data)
    if seed is None:
        return None
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()
    return digest[:_KEY_HEX_CHARS]
