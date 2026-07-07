"""OpenAI Responses SSE event formatting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import orjson

OPENAI_RESPONSES_SSE_HEADERS: dict[str, str] = {
    "X-Accel-Buffering": "no",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


def format_response_sse_event(event_type: str, data: Mapping[str, Any]) -> str:
    """Format one OpenAI Responses SSE event.

    Uses orjson on this hot path; output is compact and UTF-8 (non-ASCII
    unescaped) — still valid JSON for any spec-compliant client.
    """

    return f"event: {event_type}\ndata: {orjson.dumps(data).decode()}\n\n"
