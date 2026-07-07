"""Contract: Anthropic ``cache_control`` breakpoints survive native serialization.

Claude Code marks prompt-cache breakpoints with ``cache_control`` on system
blocks, message content blocks, and tools. Native Anthropic transports
(OpenRouter for real Claude models) must forward these verbatim or upstream
prompt caching silently stops working. Blocks use ``extra="allow"`` and the
native body comes from ``model_dump(exclude_none=True)``, so passthrough works
today — this contract pins that behavior against refactors.
"""

from __future__ import annotations

from api.models.anthropic import MessagesRequest
from core.anthropic.native_messages_request import dump_raw_messages_request

_CACHE_CONTROL = {"type": "ephemeral"}


def _request_with_cache_breakpoints() -> MessagesRequest:
    return MessagesRequest.model_validate(
        {
            "model": "claude-sonnet-4-5",
            "max_tokens": 100,
            "system": [
                {
                    "type": "text",
                    "text": "You are helpful.",
                    "cache_control": _CACHE_CONTROL,
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "hello",
                            "cache_control": _CACHE_CONTROL,
                        }
                    ],
                }
            ],
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object", "properties": {}},
                    "cache_control": _CACHE_CONTROL,
                }
            ],
        }
    )


def test_cache_control_survives_dump_on_system_blocks() -> None:
    body = dump_raw_messages_request(_request_with_cache_breakpoints())
    assert body["system"][0]["cache_control"] == _CACHE_CONTROL


def test_cache_control_survives_dump_on_message_blocks() -> None:
    body = dump_raw_messages_request(_request_with_cache_breakpoints())
    assert body["messages"][0]["content"][0]["cache_control"] == _CACHE_CONTROL


def test_cache_control_survives_dump_on_tools() -> None:
    body = dump_raw_messages_request(_request_with_cache_breakpoints())
    assert body["tools"][0]["cache_control"] == _CACHE_CONTROL
