"""Shared transport for providers with native Anthropic Messages endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Literal

import httpx

from config.constants import ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS
from core.anthropic import iter_provider_stream_error_sse_events
from core.anthropic.native_messages_request import (
    build_base_native_anthropic_request_body,
)
from core.anthropic.native_sse_block_policy import (
    NativeSseBlockPolicyState,
    transform_native_sse_block_event,
)
from core.anthropic.non_native_blocks import strip_non_native_attachment_blocks
from providers.base import (
    BaseProvider,
    ProviderConfig,
    provider_http_client,
)
from providers.error_mapping import (
    extract_provider_error_detail,
    map_error,
    user_visible_message_for_mapped_provider_error,
)
from providers.model_listing import (
    ProviderModelInfo,
    extract_openai_model_ids,
    model_infos_from_ids,
)
from providers.rate_limit import GlobalRateLimiter

from .http import maybe_await_aclose, model_list_json, raise_for_status_with_body
from .stream import AnthropicMessagesStreamRunner

StreamChunkMode = Literal["line", "event"]


class AnthropicMessagesTransport(BaseProvider):
    """Base class for providers that stream from an Anthropic-compatible endpoint."""

    stream_chunk_mode: StreamChunkMode = "line"

    # When True, image/document content blocks are stripped from the request
    # body before sending (providers without vision/document support).
    strip_non_native_blocks: bool = False

    # Auth scheme for upstream requests. ``"none"`` (the default) sends no
    # auth header — used by local providers (LM Studio, llama.cpp, Ollama)
    # that don't require credentials. Cloud providers set ``"bearer"``
    # (Kimi/Fireworks/Wafer/OpenRouter), ``"x-api-key"`` (Z.ai), or
    # ``"dual"`` (DeepSeek: x-api-key for messages, Bearer for model-list).
    auth_scheme: str = "none"

    # Anthropic API version sent on the messages request when set. Cloud
    # providers that require the version header set this to ``"2023-06-01"``;
    # local providers and DeepSeek leave it ``None``.
    anthropic_version: str | None = None

    def __init__(
        self,
        config: ProviderConfig,
        *,
        provider_name: str,
        default_base_url: str,
    ):
        super().__init__(config)
        self._provider_name = provider_name
        self._api_key = config.api_key
        self._base_url = (config.base_url or default_base_url).rstrip("/")
        self._global_rate_limiter = GlobalRateLimiter.get_scoped_instance(
            provider_name.lower(),
            rate_limit=config.rate_limit,
            rate_window=config.rate_window,
            max_concurrency=config.max_concurrency,
        )
        self._client = provider_http_client(config, base_url=self._base_url)

    async def cleanup(self) -> None:
        """Release HTTP client resources."""
        await self._client.aclose()

    async def list_model_ids(self) -> frozenset[str]:
        """Return model ids from an OpenAI-compatible ``/models`` endpoint."""
        return frozenset(info.model_id for info in await self.list_model_infos())

    async def list_model_infos(self) -> frozenset[ProviderModelInfo]:
        """Return model ids plus optional metadata from a ``/models`` endpoint."""
        response = await self._send_model_list_request()
        try:
            payload = model_list_json(response, provider_name=self._provider_name)
            return self._extract_model_infos_from_model_list_payload(payload)
        finally:
            await maybe_await_aclose(response)

    async def _send_model_list_request(self) -> httpx.Response:
        """Query the provider endpoint that advertises available model ids."""
        return await self._client.get(
            "/models",
            headers=self._model_list_headers(),
        )

    def _model_list_headers(self) -> dict[str, str]:
        """Return headers for model-list requests."""
        headers = dict(self._auth_header(for_model_list=True))
        if (version := self._model_list_anthropic_version()) is not None:
            headers["anthropic-version"] = version
        return headers

    def _auth_header(self, *, for_model_list: bool = False) -> dict[str, str]:
        """Return auth header(s) chosen by ``auth_scheme``.

        ``dual`` uses x-api-key for messages and Bearer for model-listing
        (DeepSeek). ``bearer`` always uses Bearer; ``x-api-key`` always uses
        x-api-key; ``none`` sends nothing (local providers).
        """
        if self.auth_scheme == "bearer":
            return {"Authorization": f"Bearer {self._api_key}"}
        if self.auth_scheme == "dual":
            if for_model_list:
                return {"Authorization": f"Bearer {self._api_key}"}
            return {"x-api-key": self._api_key}
        if self.auth_scheme == "x-api-key":
            return {"x-api-key": self._api_key}
        return {}

    def _model_list_anthropic_version(self) -> str | None:
        """Override to send ``anthropic-version`` on model-list requests too."""
        return None

    def _extract_model_ids_from_model_list_payload(
        self, payload: Any
    ) -> frozenset[str]:
        """Parse the provider model-list response body."""
        return extract_openai_model_ids(payload, provider_name=self._provider_name)

    def _extract_model_infos_from_model_list_payload(
        self, payload: Any
    ) -> frozenset[ProviderModelInfo]:
        """Parse provider model metadata; default to unknown capabilities."""
        return model_infos_from_ids(
            self._extract_model_ids_from_model_list_payload(payload)
        )

    def _request_headers(self) -> dict[str, str]:
        """Return headers for the native messages request."""
        if self.auth_scheme == "none" and self.anthropic_version is None:
            return {"Content-Type": "application/json"}
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        headers.update(self._auth_header())
        if self.anthropic_version is not None:
            headers["anthropic-version"] = self.anthropic_version
        return headers

    def _get_retry_request_body(self, error: Exception, body: dict) -> dict | None:
        """Return a modified request body for one retry, or ``None``.

        Providers that enforce ``input + max_tokens <= context_window`` (and
        reject oversized requests with a 400 instead of truncating) override
        this to clamp ``max_tokens`` after a context-length error.
        """
        return None

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build a native Anthropic request body."""
        thinking_enabled = self._is_thinking_enabled(request, thinking_enabled)
        return build_base_native_anthropic_request_body(
            request,
            default_max_tokens=ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS,
            thinking_enabled=thinking_enabled,
        )

    def _maybe_strip_non_native_blocks(self, body: dict) -> None:
        """Strip image/document blocks when the provider cannot handle them."""
        if not self.strip_non_native_blocks:
            return
        if "messages" in body:
            body["messages"] = strip_non_native_attachment_blocks(
                body["messages"], provider_name=self._provider_name
            )

    def _merged_request_headers(
        self, extra_headers: dict[str, str] | None
    ) -> dict[str, str]:
        """Merge per-request extras over the provider's base request headers."""
        headers = self._request_headers()
        if extra_headers:
            headers = {**headers, **extra_headers}
        return headers

    async def _send_stream_request(
        self, body: dict, *, extra_headers: dict[str, str] | None = None
    ) -> httpx.Response:
        """Create a streaming messages response."""
        request = self._client.build_request(
            "POST",
            "/messages",
            json=body,
            headers=self._merged_request_headers(extra_headers),
        )
        return await self._client.send(request, stream=True)

    async def _raise_for_status(
        self, response: httpx.Response, *, req_tag: str
    ) -> None:
        """Raise for non-200 responses after attaching safe error metadata."""
        await raise_for_status_with_body(
            response,
            provider_name=self._provider_name,
            req_tag=req_tag,
            log_api_error_tracebacks=self._config.log_api_error_tracebacks,
        )

    def _new_stream_state(self, request: Any, *, thinking_enabled: bool) -> Any:
        """Return per-stream provider state for event transformation."""
        if self.stream_chunk_mode == "line":
            return NativeSseBlockPolicyState()
        return None

    def _transform_stream_event(
        self,
        event: str,
        state: Any,
        *,
        thinking_enabled: bool,
    ) -> str | None:
        """Transform or drop a grouped SSE event before yielding it downstream."""
        if isinstance(state, NativeSseBlockPolicyState):
            return transform_native_sse_block_event(
                event, state, thinking_enabled=thinking_enabled
            )
        return event

    def _get_error_message(self, error: Exception, request_id: str | None) -> str:
        """Map an exception into a user-facing provider error message."""
        mapped_error = map_error(error, rate_limiter=self._global_rate_limiter)
        return user_visible_message_for_mapped_provider_error(
            mapped_error,
            provider_name=self._provider_name,
            read_timeout_s=self._config.http_read_timeout,
            detail=extract_provider_error_detail(error),
            request_id=request_id,
        )

    async def _validated_stream_send(
        self,
        body: dict,
        *,
        req_tag: str,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send request and raise mapped HTTP errors before yielding body chunks.

        The initial upstream send is wrapped through the rate limiter's
        ``execute_with_retry`` so that transient 429/5xx responses are retried
        with backoff.  Callers (stream runner, recovery) must NOT double-wrap
        this method with ``execute_with_retry`` — that would compound retries.
        """

        async def _send_and_validate() -> httpx.Response:
            send_response = await self._send_stream_request(
                body, extra_headers=extra_headers
            )
            if send_response.status_code != 200:
                try:
                    await self._raise_for_status(send_response, req_tag=req_tag)
                finally:
                    if not send_response.is_closed:
                        await maybe_await_aclose(send_response)
            return send_response

        return await self._global_rate_limiter.execute_with_retry(_send_and_validate)

    def _emit_error_events(
        self,
        *,
        request: Any,
        input_tokens: int,
        error_message: str,
        sent_any_event: bool,
    ) -> Iterator[str]:
        """Emit the same Anthropic message lifecycle used by OpenAI-chat providers."""
        yield from iter_provider_stream_error_sse_events(
            request=request,
            input_tokens=input_tokens,
            error_message=error_message,
            sent_any_event=sent_any_event,
            log_raw_sse_events=self._config.log_raw_sse_events,
        )

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
        thinking_enabled: bool | None = None,
    ) -> AsyncIterator[str]:
        """Stream response via a native Anthropic-compatible messages endpoint."""
        runner = AnthropicMessagesStreamRunner(
            self,
            request=request,
            input_tokens=input_tokens,
            request_id=request_id,
            thinking_enabled=thinking_enabled,
        )
        async for event in runner.run():
            yield event
