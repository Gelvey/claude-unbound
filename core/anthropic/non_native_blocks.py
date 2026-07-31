"""Shared utility for stripping non-native content blocks from request bodies.

Providers that lack vision/document support (e.g. DeepSeek) must not receive
``image`` or ``document`` content blocks.  Claude Code typically sends PDFs as
``document`` blocks alongside a ``tool_result`` that already contains the
extracted text, so stripping the attachment preserves the request instead of
failing with an unsupported-block error.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# Block types silently stripped for providers without vision/document support.
_STRIPPABLE_MESSAGE_BLOCK_TYPES = frozenset({"image", "document"})


def _omitted_attachment_block(provider_name: str) -> dict[str, str]:
    """Return the placeholder text block for a stripped attachment."""
    return {
        "type": "text",
        "text": (
            f"[attachment omitted: {provider_name} does not support "
            "image or document inputs]"
        ),
    }


def strip_non_native_attachment_blocks(
    messages: Any,
    *,
    provider_name: str,
) -> Any:
    """Remove image/document blocks that the provider cannot process.

    Returns a new list with ``image``/``document`` blocks removed from both
    top-level message content and nested ``tool_result.content``.  When a
    message or tool_result would be left empty, a placeholder text block is
    inserted so the request shape remains valid.

    A warning is logged when any blocks are stripped.
    """
    if not isinstance(messages, list):
        return messages

    omitted_block = _omitted_attachment_block(provider_name)
    stripped: list[Any] = []
    top_level_dropped: dict[str, int] = {}
    nested_dropped: dict[str, int] = {}
    placeholder_replacements = 0

    for message in messages:
        if not isinstance(message, dict):
            stripped.append(message)
            continue
        content = message.get("content")
        if not isinstance(content, list):
            stripped.append(message)
            continue

        new_content: list[Any] = []
        message_dropped_attachment = False
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype in _STRIPPABLE_MESSAGE_BLOCK_TYPES:
                    top_level_dropped[btype] = top_level_dropped.get(btype, 0) + 1
                    message_dropped_attachment = True
                    continue
                if btype == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, list):
                        filtered_inner: list[Any] = []
                        for sub in inner:
                            if (
                                isinstance(sub, dict)
                                and sub.get("type") in _STRIPPABLE_MESSAGE_BLOCK_TYPES
                            ):
                                sub_type = sub["type"]
                                nested_dropped[sub_type] = (
                                    nested_dropped.get(sub_type, 0) + 1
                                )
                                continue
                            filtered_inner.append(sub)
                        if not filtered_inner:
                            filtered_inner = [omitted_block]
                            placeholder_replacements += 1
                        new_block = dict(block)
                        new_block["content"] = filtered_inner
                        new_content.append(new_block)
                        continue
            new_content.append(block)
        if not new_content and message_dropped_attachment:
            new_content = [omitted_block]
            placeholder_replacements += 1
        new_msg = dict(message)
        new_msg["content"] = new_content
        stripped.append(new_msg)

    if top_level_dropped or nested_dropped:
        logger.warning(
            "{}_REQUEST: stripped unsupported attachment blocks "
            "(top_level={} nested_in_tool_result={} placeholder_tool_results={}). "
            "{} has no vision/document support; the model will not see this content.",
            provider_name,
            dict(top_level_dropped),
            dict(nested_dropped),
            placeholder_replacements,
            provider_name,
        )
    return stripped
