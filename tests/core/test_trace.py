"""Structured TRACE logging assertions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from loguru import logger

from config.logging_config import configure_logging
from core.trace import (
    TRACE_PAYLOAD_BINDING,
    configure_trace_payloads,
    trace_event,
    traced_async_stream,
)


def _json_log_rows(log_file: str) -> list[dict]:
    logger.complete()
    text = Path(log_file).read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.split("\n")]


def test_trace_payload_merged_into_json_line(tmp_path) -> None:
    log_file = str(tmp_path / "t.log")
    configure_logging(log_file, force=True)
    trace_event(stage="s", event="e.v1", source="unit", hello="world", n=42)
    row = _json_log_rows(log_file)[-1]
    assert row["trace"] is True
    assert row["stage"] == "s"
    assert row["event"] == "e.v1"
    assert row["source"] == "unit"
    assert row["hello"] == "world"
    assert row["n"] == 42
    assert TRACE_PAYLOAD_BINDING == "trace_payload"


@pytest.fixture(autouse=True)
def _reset_trace_payload_mode():
    """Keep the module-level full-payload flag isolated per test."""
    configure_trace_payloads(False)
    yield
    configure_trace_payloads(False)


def test_snapshot_truncates_long_text_by_default() -> None:
    from core.trace import provider_chat_body_snapshot

    long_text = "x" * 1000
    snap = provider_chat_body_snapshot(
        {"model": "m", "messages": [{"role": "user", "content": long_text}]}
    )
    content = snap["messages"][0]["content"]
    assert long_text not in str(content)
    assert content.startswith("x" * 200)
    assert "[1000 chars]" in content
    # Short fields stay verbatim
    assert snap["model"] == "m"


def test_snapshot_keeps_full_text_when_full_payloads_enabled() -> None:
    from core.trace import provider_chat_body_snapshot

    long_text = "y" * 1000
    configure_trace_payloads(True)
    snap = provider_chat_body_snapshot(
        {"model": "m", "messages": [{"role": "user", "content": long_text}]}
    )
    assert snap["messages"][0]["content"] == long_text


def test_api_messages_request_snapshot_truncates_system_text() -> None:
    from core.trace import api_messages_request_snapshot

    long_system = "s" * 500
    snap = api_messages_request_snapshot(
        {
            "model": "m",
            "system": long_system,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10,
        }
    )
    assert "[500 chars]" in snap["system"]
    assert snap["max_tokens"] == 10
    assert snap["messages"][0]["content"] == "hi"


def test_native_snapshot_truncation_preserves_redaction() -> None:
    from core.trace import provider_native_messages_body_snapshot

    snap = provider_native_messages_body_snapshot(
        {"model": "m", "metadata": {"api_key": "secret" * 100}}
    )
    assert snap["metadata"]["api_key"] == "<redacted>"


def test_sanitize_masks_nested_api_key_strings() -> None:
    """Credential-shaped keys redact without touching normal message text."""
    from core.trace import _sanitize_trace_value

    out = _sanitize_trace_value(
        {"outer": {"api_key": "secret", "text": "visible"}},
    )
    assert out["outer"]["api_key"] == "<redacted>"
    assert out["outer"]["text"] == "visible"


@pytest.mark.asyncio
async def test_traced_async_stream_logs_completion(tmp_path) -> None:
    log_file = str(tmp_path / "complete.log")
    configure_logging(log_file, force=True)

    async def source():
        yield "hello"
        yield " world"

    chunks = [
        chunk
        async for chunk in traced_async_stream(
            source(),
            stage="egress",
            source="unit",
            complete_event="stream.completed",
            interrupted_event="stream.interrupted",
            extra={"request_id": "req_complete"},
        )
    ]

    assert chunks == ["hello", " world"]
    rows = _json_log_rows(log_file)
    completed = [row for row in rows if row.get("event") == "stream.completed"]
    assert len(completed) == 1
    assert completed[0]["request_id"] == "req_complete"
    assert completed[0]["stream_chunks"] == 2
    assert completed[0]["outcome"] == "ok"


@pytest.mark.asyncio
async def test_traced_async_stream_logs_real_exception(tmp_path) -> None:
    log_file = str(tmp_path / "error.log")
    configure_logging(log_file, force=True)

    async def source():
        yield "before"
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        async for _chunk in traced_async_stream(
            source(),
            stage="egress",
            source="unit",
            complete_event="stream.completed",
            interrupted_event="stream.interrupted",
            extra={"request_id": "req_error"},
        ):
            pass

    rows = _json_log_rows(log_file)
    interrupted = [row for row in rows if row.get("event") == "stream.interrupted"]
    assert len(interrupted) == 1
    assert interrupted[0]["request_id"] == "req_error"
    assert interrupted[0]["stream_chunks"] == 1
    assert interrupted[0]["outcome"] == "error"
    assert interrupted[0]["exc_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_traced_async_stream_closes_quietly_on_generator_exit(tmp_path) -> None:
    log_file = str(tmp_path / "generator_exit.log")
    configure_logging(log_file, force=True)

    async def source():
        yield "first"
        yield "second"

    stream = traced_async_stream(
        source(),
        stage="egress",
        source="unit",
        complete_event="stream.completed",
        interrupted_event="stream.interrupted",
        extra={"request_id": "req_closed"},
    )

    assert await anext(stream) == "first"
    await stream.aclose()

    rows = _json_log_rows(log_file)
    events = {row.get("event") for row in rows}
    assert "stream.completed" not in events
    assert "stream.interrupted" not in events
