"""OpenRouter provider implementation."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from loguru import logger

from core.anthropic import iter_provider_stream_error_sse_events
from core.anthropic.native_messages_request import OpenRouterPolicySettings
from core.anthropic.native_sse_block_policy import (
    NativeSseBlockPolicyState,
    is_terminal_openrouter_done_event,
    parse_native_sse_event,
    transform_native_sse_block_event,
)
from providers.base import ProviderConfig
from providers.defaults import OPENROUTER_DEFAULT_BASE
from providers.model_listing import (
    ProviderModelInfo,
    extract_openrouter_tool_model_ids,
    extract_openrouter_tool_model_infos,
)
from providers.transports.anthropic_messages import (
    AnthropicMessagesTransport,
    StreamChunkMode,
)
from providers.transports.openai_chat import context_length_clamped_retry_body

from .request import build_request_body


class OpenRouterProvider(AnthropicMessagesTransport):
    """OpenRouter provider using the native Anthropic-compatible messages API."""

    stream_chunk_mode: StreamChunkMode = "event"
    auth_scheme = "bearer"
    anthropic_version = "2023-06-01"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        settings: OpenRouterPolicySettings | None = None,
    ):
        super().__init__(
            config,
            provider_name="OPENROUTER",
            default_base_url=OPENROUTER_DEFAULT_BASE,
        )
        # Settings is optional so existing tests that build the provider from
        # a bare ProviderConfig keep working. Production code (the registry)
        # always passes the live settings instance.
        self._settings: OpenRouterPolicySettings | None = settings

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Internal helper for tests and direct request dispatch."""
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
            settings=self._settings,
        )

    def _get_retry_request_body(self, error: Exception, body: dict) -> dict | None:
        """Retry once with clamped ``max_tokens`` after a context-length 400.

        OpenRouter enforces ``input + max_tokens <= context_window`` and 400s
        instead of truncating, which breaks clients that send a large fixed
        ``max_tokens`` (e.g. Claude Code subagents).
        """
        retry_body = context_length_clamped_retry_body(error, body)
        if retry_body is not None:
            logger.warning(
                "OPENROUTER_STREAM: clamping max_tokens {} -> {} after "
                "context-length error",
                body.get("max_tokens"),
                retry_body["max_tokens"],
            )
        return retry_body

    def _extract_model_ids_from_model_list_payload(
        self, payload: Any
    ) -> frozenset[str]:
        """Only advertise OpenRouter models that can run Claude Code tools."""
        return extract_openrouter_tool_model_ids(
            payload, provider_name=self._provider_name
        )

    def _extract_model_infos_from_model_list_payload(
        self, payload: Any
    ) -> frozenset[ProviderModelInfo]:
        """Advertise OpenRouter tool models with reasoning capability metadata."""
        return extract_openrouter_tool_model_infos(
            payload, provider_name=self._provider_name
        )

    def _new_stream_state(self, request: Any, *, thinking_enabled: bool) -> Any:
        """Create per-stream state for thinking block filtering."""
        return NativeSseBlockPolicyState()

    def _transform_stream_event(
        self,
        event: str,
        state: Any,
        *,
        thinking_enabled: bool,
    ) -> str | None:
        """Drop provider-specific terminal noise and hidden thinking events."""
        if isinstance(state, NativeSseBlockPolicyState):
            event_name, data_text = parse_native_sse_event(event)
            if state.message_stopped or is_terminal_openrouter_done_event(
                event_name, data_text
            ):
                return None
            if event_name == "message_stop":
                state.message_stopped = True

        if isinstance(state, NativeSseBlockPolicyState):
            return transform_native_sse_block_event(
                event, state, thinking_enabled=thinking_enabled
            )
        return event

    def _emit_error_events(
        self,
        *,
        request: Any,
        input_tokens: int,
        error_message: str,
        sent_any_event: bool,
    ) -> Iterator[str]:
        """Emit the Anthropic SSE error shape expected by Claude clients."""
        yield from iter_provider_stream_error_sse_events(
            request=request,
            input_tokens=input_tokens,
            error_message=error_message,
            sent_any_event=sent_any_event,
            log_raw_sse_events=self._config.log_raw_sse_events,
        )
