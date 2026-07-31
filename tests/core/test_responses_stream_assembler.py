"""Unit tests for ResponsesStreamAssembler — index allocation, block open/close, errors."""

from __future__ import annotations

import json

from core.openai_responses.anthropic_sse import AnthropicSseEvent
from core.openai_responses.stream_state import ResponsesStreamAssembler


def _sse(event: str, data: dict) -> AnthropicSseEvent:
    return AnthropicSseEvent(event=event, data=data)


def _parse_chunks(chunks: list[str]) -> list[tuple[str, dict]]:
    """Parse SSE chunks into (event, data) pairs."""
    pairs: list[tuple[str, dict]] = []
    for chunk in chunks:
        for block in chunk.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            event_name = ""
            data_parts: list[str] = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_parts.append(line.split(":", 1)[1].strip())
            data = json.loads("\n".join(data_parts)) if data_parts else {}
            pairs.append((event_name, data))
    return pairs


def _make_assembler() -> ResponsesStreamAssembler:
    return ResponsesStreamAssembler({"model": "nvidia_nim/test-model", "stream": True})


# ─── Index allocation ───────────────────────────────────────────────────────


def test_text_block_start_allocates_output_index():
    """content_block_start with a text block allocates a new output slot."""
    assembler = _make_assembler()
    chunks = assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        )
    )
    events = _parse_chunks(chunks)
    # response.created is emitted first (ensure_started)
    assert events[0][0] == "response.created"
    assert events[1][0] == "response.output_item.added"
    assert events[1][1]["output_index"] == 0


def test_reasoning_block_start_allocates_output_index():
    """content_block_start with a thinking block allocates a new output slot."""
    assembler = _make_assembler()
    chunks = assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": ""},
            },
        )
    )
    events = _parse_chunks(chunks)
    assert events[1][0] == "response.output_item.added"
    assert events[1][1]["output_index"] == 0


def test_tool_block_start_allocates_output_index():
    """content_block_start with a tool_use block allocates a new output slot."""
    assembler = _make_assembler()
    chunks = assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "echo",
                    "input": {},
                },
            },
        )
    )
    events = _parse_chunks(chunks)
    assert events[1][0] == "response.output_item.added"
    assert events[1][1]["output_index"] == 0
    assert events[1][1]["item"]["type"] == "function_call"


def test_multiple_blocks_get_sequential_output_indices():
    """Multiple blocks opened in sequence get incremental output indices."""
    assembler = _make_assembler()
    indices: list[int] = []
    for i in range(3):
        chunks = assembler.process_anthropic_event(
            _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": i,
                    "content_block": {"type": "text", "text": ""},
                },
            )
        )
        events = _parse_chunks(chunks)
        added_events = [e for e in events if e[0] == "response.output_item.added"]
        indices.append(added_events[0][1]["output_index"])
    assert indices == [0, 1, 2]


def test_fallback_text_index_for_missing_event_index():
    """When event has no index, a negative fallback index is allocated."""
    assembler = _make_assembler()
    # content_block_delta with text_delta but no matching block → auto-creates
    chunks = assembler.process_anthropic_event(
        _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "hello"},
            },
        )
    )
    events = _parse_chunks(chunks)
    # Should auto-create a text block with fallback index -1
    assert any(e[0] == "response.output_item.added" for e in events)
    added = next(e for e in events if e[0] == "response.output_item.added")
    assert added[1]["output_index"] == 0


# ─── Block open/close ────────────────────────────────────────────────────────


def test_text_block_open_close_emits_full_lifecycle():
    """A text block goes through added → delta → done → output_item.done."""
    assembler = _make_assembler()
    all_chunks: list[str] = []

    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": "Hi"},
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": " world"},
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        )
    )
    all_chunks.extend(assembler.complete_response())

    events = _parse_chunks(all_chunks)
    event_names = [e[0] for e in events]
    assert "response.created" in event_names
    assert "response.output_item.added" in event_names
    assert "response.output_text.delta" in event_names
    assert "response.output_text.done" in event_names
    assert "response.content_part.done" in event_names
    assert "response.output_item.done" in event_names
    assert "response.completed" in event_names

    # Verify the completed text is the concatenation of deltas
    done_event = next(e for e in events if e[0] == "response.output_text.done")
    assert done_event[1]["text"] == "Hi world"


def test_reasoning_block_open_close_emits_reasoning_lifecycle():
    """A thinking block emits reasoning_text.delta and output_item.done."""
    assembler = _make_assembler()
    all_chunks: list[str] = []

    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "thinking", "thinking": "thought"},
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": " more"},
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        )
    )
    all_chunks.extend(assembler.complete_response())

    events = _parse_chunks(all_chunks)
    event_names = [e[0] for e in events]
    assert "response.reasoning_text.delta" in event_names
    assert "response.reasoning_text.done" in event_names
    assert "response.output_item.done" in event_names
    assert "response.completed" in event_names

    done_event = next(e for e in events if e[0] == "response.reasoning_text.done")
    assert done_event[1]["text"] == "thought more"


def test_tool_block_open_close_emits_function_call():
    """A tool_use block emits function_call_arguments.done and output_item.done."""
    assembler = _make_assembler()
    all_chunks: list[str] = []

    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "echo",
                        "input": {},
                    },
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": '{"value":"FCC"}',
                    },
                },
            )
        )
    )
    all_chunks.extend(
        assembler.process_anthropic_event(
            _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        )
    )
    all_chunks.extend(assembler.complete_response())

    events = _parse_chunks(all_chunks)
    event_names = [e[0] for e in events]
    assert "response.function_call_arguments.delta" in event_names
    assert "response.function_call_arguments.done" in event_names
    assert "response.output_item.done" in event_names
    assert "response.completed" in event_names

    done = next(e for e in events if e[0] == "response.function_call_arguments.done")
    assert done[1]["arguments"] == '{"value":"FCC"}'


def test_complete_response_flushes_active_blocks():
    """complete_response flushes any blocks that were never explicitly stopped."""
    assembler = _make_assembler()
    # Open a text block but never send content_block_stop
    assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": "orphan"},
            },
        )
    )
    chunks = assembler.complete_response()
    events = _parse_chunks(chunks)
    # The orphan block should still be completed
    assert any(e[0] == "response.output_item.done" for e in events)
    assert any(e[0] == "response.completed" for e in events)
    assert assembler.terminal is True


def test_terminal_assembler_ignores_further_events():
    """After terminal, subsequent events produce no chunks."""
    assembler = _make_assembler()
    assembler.complete_response()
    chunks = assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": "late"},
            },
        )
    )
    assert chunks == []


def test_finish_if_needed_completes_unstarted_assembler():
    """finish_if_needed on a fresh assembler emits response.created + completed."""
    assembler = _make_assembler()
    chunks = assembler.finish_if_needed()
    events = _parse_chunks(chunks)
    event_names = [e[0] for e in events]
    assert "response.created" in event_names
    assert "response.completed" in event_names
    assert assembler.terminal is True


# ─── Mid-stream error handling ──────────────────────────────────────────────


def test_error_event_produces_response_failed():
    """An error event mid-stream flushes active blocks and emits response.failed."""
    assembler = _make_assembler()
    # Open a text block first so error flushes it
    assembler.process_anthropic_event(
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": "partial"},
            },
        )
    )
    error_chunks = assembler.process_anthropic_event(
        _sse(
            "error",
            {
                "type": "error",
                "error": {"type": "api_error", "message": "provider failed"},
            },
        )
    )
    events = _parse_chunks(error_chunks)
    # Should flush the active text block then emit response.failed
    event_names = [e[0] for e in events]
    assert "response.output_item.done" in event_names
    assert "response.failed" in event_names
    assert assembler.terminal is True

    failed_event = next(e for e in events if e[0] == "response.failed")
    response = failed_event[1]["response"]
    assert response["status"] == "failed"
    assert response["error"]["message"] == "provider failed"
    assert response["error"]["type"] == "api_error"
    assert response["error"]["param"] is None
    assert response["error"]["code"] is None


def test_error_event_with_missing_error_field_uses_fallback():
    """An error event without an 'error' dict still produces a response.failed."""
    assembler = _make_assembler()
    error_chunks = assembler.process_anthropic_event(
        _sse("error", {"type": "error"}),
    )
    events = _parse_chunks(error_chunks)
    assert any(e[0] == "response.failed" for e in events)
    failed = next(e for e in events if e[0] == "response.failed")
    assert failed[1]["response"]["status"] == "failed"
    assert failed[1]["response"]["error"]["type"] == "api_error"


def test_message_delta_sets_usage_tokens():
    """message_delta with usage info populates the final response usage."""
    assembler = _make_assembler()
    assembler.process_anthropic_event(
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"input_tokens": 5, "output_tokens": 10},
            },
        )
    )
    chunks = assembler.complete_response()
    events = _parse_chunks(chunks)
    completed = next(e for e in events if e[0] == "response.completed")
    usage = completed[1]["response"]["usage"]
    assert usage["input_tokens"] == 5
    assert usage["output_tokens"] == 10
    assert usage["total_tokens"] == 15


def test_message_stop_triggers_complete_response():
    """A message_stop event is treated as completion and emits response.completed."""
    assembler = _make_assembler()
    chunks = assembler.process_anthropic_event(
        _sse("message_stop", {"type": "message_stop"}),
    )
    events = _parse_chunks(chunks)
    assert any(e[0] == "response.created" for e in events)
    assert any(e[0] == "response.completed" for e in events)
    assert assembler.terminal is True


def test_response_payload_reflects_request_fields():
    """response_payload includes model, tool_choice, and temperature from request."""
    assembler = ResponsesStreamAssembler(
        {
            "model": "open_router/test-model",
            "stream": True,
            "tool_choice": "required",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_output_tokens": 256,
            "parallel_tool_calls": False,
        }
    )
    payload = assembler.response_payload(status="in_progress")
    assert payload["model"] == "open_router/test-model"
    assert payload["tool_choice"] == "required"
    assert payload["temperature"] == 0.7
    assert payload["top_p"] == 0.9
    assert payload["max_output_tokens"] == 256
    assert payload["parallel_tool_calls"] is False
    assert payload["status"] == "in_progress"
    assert payload["error"] is None
