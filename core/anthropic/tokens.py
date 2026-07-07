"""Token estimation for Anthropic-compatible requests.

Counting re-encodes conversation text with tiktoken synchronously, so a
bounded memo caches per-message / system / per-tool counts keyed by content
hash. Conversations are append-only: every message except the newest hits the
cache, dropping per-request cost from O(history) to O(new message).
"""

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import tiktoken
from loguru import logger

from .content import get_block_attr

# Lazily initialized: tiktoken.get_encoding() loads (and on first ever run,
# downloads) the BPE ranks. Doing that at import time slows startup and can
# crash the server when offline before any request needs token counting.
_encoder: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    """Return the shared cl100k_base encoder, loading it on first use."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


_DISALLOWED_SPECIAL: tuple[str, ...] = ()

_TOKEN_MEMO_MAX_ENTRIES = 4096
_token_memo: OrderedDict[bytes, int] = OrderedDict()


def clear_token_count_memo() -> None:
    """Reset the bounded token-count memo (tests / diagnostics)."""
    _token_memo.clear()


def token_count_memo_size() -> int:
    """Current number of memoized entries (tests / diagnostics)."""
    return len(_token_memo)


def _memoized_count(
    category: str, key_material: str | None, compute: Callable[[], int]
) -> int:
    """Return ``compute()`` cached under a hash of ``key_material``.

    ``key_material=None`` disables caching for that item (unhashable input).
    """
    if key_material is None:
        return compute()
    key = hashlib.sha256(
        f"{category}\x00{key_material}".encode("utf-8", errors="replace")
    ).digest()
    cached = _token_memo.get(key)
    if cached is not None:
        _token_memo.move_to_end(key)
        return cached
    value = compute()
    _token_memo[key] = value
    if len(_token_memo) > _TOKEN_MEMO_MAX_ENTRIES:
        _token_memo.popitem(last=False)
    return value


def _stable_key_material(obj: Any) -> str | None:
    """Serialize an object into deterministic cache-key material, or None."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        parts = [_stable_key_material(item) for item in obj]
        if any(part is None for part in parts):
            return None
        return "\x00".join(part for part in parts if part is not None)
    dump_json = getattr(obj, "model_dump_json", None)
    if callable(dump_json):
        try:
            dumped = dump_json()
        except TypeError, ValueError:
            return None
        # Mocks and duck-typed objects may return non-strings; refuse to
        # cache rather than build an unstable key.
        return dumped if isinstance(dumped, str) else None
    try:
        # No ``default=`` fallback: reprs of arbitrary objects may embed
        # reusable memory addresses, which would poison cache keys.
        return json.dumps(obj, sort_keys=True)
    except TypeError, ValueError:
        return None


def _count_text_tokens(text: str) -> int:
    return len(get_encoder().encode(text, disallowed_special=_DISALLOWED_SPECIAL))


def _count_system_tokens(system: str | list) -> int:
    total_tokens = 0
    if isinstance(system, str):
        total_tokens += _count_text_tokens(system)
    elif isinstance(system, list):
        for block in system:
            text = get_block_attr(block, "text", "")
            if text:
                total_tokens += _count_text_tokens(str(text))
    return total_tokens + 4


def get_token_count(
    messages: list,
    system: str | list | None = None,
    tools: list | None = None,
) -> int:
    """Estimate token count for a request."""
    total_tokens = 0

    if system:
        total_tokens += _memoized_count(
            "system",
            _stable_key_material(system),
            lambda: _count_system_tokens(system),
        )

    for msg in messages:
        total_tokens += _memoized_count(
            "message",
            _stable_key_material(msg),
            lambda m=msg: _count_message_tokens(m),
        )

    if tools:
        for tool in tools:
            tool_str = (
                tool.name + (tool.description or "") + json.dumps(tool.input_schema)
            )
            total_tokens += _memoized_count(
                "tool", tool_str, lambda s=tool_str: _count_text_tokens(s)
            )
        total_tokens += len(tools) * 5

    total_tokens += len(messages) * 4

    return max(1, total_tokens)


def _count_message_tokens(msg: Any) -> int:
    """Count tokens for one message's content blocks."""
    total_tokens = 0
    if isinstance(msg.content, str):
        total_tokens += _count_text_tokens(msg.content)
    elif isinstance(msg.content, list):
        for block in msg.content:
            b_type = get_block_attr(block, "type") or None

            if b_type == "text":
                text = get_block_attr(block, "text", "")
                total_tokens += _count_text_tokens(str(text))
            elif b_type == "thinking":
                thinking = get_block_attr(block, "thinking", "")
                total_tokens += _count_text_tokens(str(thinking))
            elif b_type == "tool_use":
                name = get_block_attr(block, "name", "")
                inp = get_block_attr(block, "input", {})
                block_id = get_block_attr(block, "id", "")
                total_tokens += _count_text_tokens(str(name))
                total_tokens += _count_text_tokens(json.dumps(inp))
                total_tokens += _count_text_tokens(str(block_id))
                total_tokens += 15
            elif b_type == "image":
                source = get_block_attr(block, "source")
                if isinstance(source, dict):
                    data = source.get("data") or source.get("base64") or ""
                    if data:
                        total_tokens += max(85, len(data) // 3000)
                    else:
                        total_tokens += 765
                else:
                    total_tokens += 765
            elif b_type == "tool_result":
                content = get_block_attr(block, "content", "")
                tool_use_id = get_block_attr(block, "tool_use_id", "")
                if isinstance(content, str):
                    total_tokens += _count_text_tokens(content)
                else:
                    total_tokens += _count_text_tokens(json.dumps(content))
                total_tokens += _count_text_tokens(str(tool_use_id))
                total_tokens += 8
            elif b_type in (
                "server_tool_use",
                "web_search_tool_result",
                "web_fetch_tool_result",
            ):
                if hasattr(block, "model_dump"):
                    blob: object = block.model_dump()
                else:
                    blob = block
                try:
                    total_tokens += _count_text_tokens(
                        json.dumps(blob, default=str, ensure_ascii=False)
                    )
                except (TypeError, ValueError, OverflowError) as e:
                    logger.debug("Block encode fallback b_type={} err={}", b_type, e)
                    total_tokens += _count_text_tokens(str(blob))
                total_tokens += 12
            else:
                logger.debug(
                    "Unexpected block type %r, falling back to json/str encoding",
                    b_type,
                )
                try:
                    total_tokens += _count_text_tokens(json.dumps(block))
                except TypeError, ValueError:
                    total_tokens += _count_text_tokens(str(block))

    return total_tokens
