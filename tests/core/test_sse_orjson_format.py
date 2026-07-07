"""orjson-backed SSE event formatting stays wire-compatible."""

from __future__ import annotations

import json

from core.anthropic.sse import format_sse_event
from core.openai_responses.events import format_response_sse_event

_PAYLOAD = {
    "type": "content_block_delta",
    "index": 0,
    "delta": {"type": "text_delta", "text": 'quote " backslash \\ newline \n'},
}

_NON_ASCII = {"type": "text", "text": "héllo — ünïcode ✓ 中文"}


def _parse(event: str, event_type: str) -> dict:
    lines = event.split("\n")
    assert lines[0] == f"event: {event_type}"
    assert lines[1].startswith("data: ")
    assert event.endswith("\n\n")
    return json.loads(lines[1][len("data: ") :])


def test_anthropic_sse_event_round_trips() -> None:
    event = format_sse_event("content_block_delta", _PAYLOAD)
    assert _parse(event, "content_block_delta") == _PAYLOAD


def test_anthropic_sse_event_non_ascii_round_trips() -> None:
    event = format_sse_event("content_block_delta", _NON_ASCII)
    assert _parse(event, "content_block_delta") == _NON_ASCII


def test_anthropic_sse_data_is_single_line() -> None:
    # orjson must escape embedded newlines; a literal \n would break SSE framing.
    event = format_sse_event("content_block_delta", _PAYLOAD)
    assert len(event.split("\n\n")[0].split("\n")) == 2


def test_responses_sse_event_round_trips() -> None:
    payload = {
        "type": "response.output_text.delta",
        "delta": "hi",
        "sequence_number": 3,
    }
    event = format_response_sse_event("response.output_text.delta", payload)
    assert _parse(event, "response.output_text.delta") == payload


def test_responses_sse_event_non_ascii_round_trips() -> None:
    event = format_response_sse_event("response.completed", _NON_ASCII)
    assert _parse(event, "response.completed") == _NON_ASCII
