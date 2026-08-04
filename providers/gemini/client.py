"""Google AI Studio Gemini provider (OpenAI-compatible chat completions)."""

from __future__ import annotations

from typing import Any

from providers.base import ProviderConfig
from providers.defaults import GEMINI_DEFAULT_BASE
from providers.transports.openai_chat import OpenAIChatTransport
from providers.transports.openai_chat.google_signatures import (
    record_tool_call_extra_content,
)

from .request import build_request_body


class GeminiProvider(OpenAIChatTransport):
    """Gemini API using ``https://generativelanguage.googleapis.com/v1beta/openai/``."""

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="GEMINI",
            base_url=config.base_url or GEMINI_DEFAULT_BASE,
            api_key=config.api_key,
        )
        self._tool_call_extra_content_by_id: dict[str, dict[str, Any]] = {}

    def _record_tool_call_extra_content(
        self, tool_call_id: str, extra_content: dict[str, Any]
    ) -> None:
        record_tool_call_extra_content(
            self._tool_call_extra_content_by_id, tool_call_id, extra_content
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
            tool_call_extra_content_by_id=self._tool_call_extra_content_by_id,
        )
