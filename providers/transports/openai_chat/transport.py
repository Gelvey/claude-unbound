"""OpenAI-compatible chat transport base."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
from loguru import logger
from openai import AsyncOpenAI

from core.anthropic import SSEBuilder
from core.anthropic.session_key import stable_session_key
from providers.base import (
    BaseProvider,
    ProviderConfig,
    provider_http_limits,
    provider_http_timeout,
)
from providers.error_mapping import (
    extract_provider_error_detail,
    map_error,
    user_visible_message_for_mapped_provider_error,
)
from providers.model_listing import extract_openai_model_ids
from providers.rate_limit import GlobalRateLimiter

from .context_length import openai_error_text
from .stream import OpenAIChatStreamRunner


class OpenAIChatTransport(BaseProvider):
    """Base for OpenAI-compatible ``/chat/completions`` adapters."""

    # Request final-chunk usage reporting (actual prompt/completion/cached-token
    # counts) on streams. Providers that reject the parameter can set this to
    # False; a 400 naming ``stream_options`` also disables it automatically.
    include_stream_usage: bool = True

    # Opt-in: send the stable conversation key as ``prompt_cache_key`` for
    # providers documented to support prompt-cache routing by that field.
    include_prompt_cache_key: bool = False

    def __init__(
        self,
        config: ProviderConfig,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
    ):
        super().__init__(config)
        self._provider_name = provider_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._global_rate_limiter = GlobalRateLimiter.get_scoped_instance(
            provider_name.lower(),
            rate_limit=config.rate_limit,
            rate_window=config.rate_window,
            max_concurrency=config.max_concurrency,
        )
        # Always create an explicit httpx client so keep-alive is controlled
        # here instead of falling back to httpx's 5s default expiry. Kept on
        # self so ancillary requests (e.g. model discovery) warm the same pool.
        self._http_client = httpx.AsyncClient(
            proxy=config.proxy or None,
            timeout=provider_http_timeout(config),
            limits=provider_http_limits(config),
            http2=config.http2,
        )
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=0,
            timeout=provider_http_timeout(config),
            http_client=self._http_client,
        )

    async def cleanup(self) -> None:
        """Release HTTP client resources."""
        client = getattr(self, "_client", None)
        if client is not None:
            await client.close()

    async def list_model_ids(self) -> frozenset[str]:
        """Return model ids from the provider's OpenAI-compatible models endpoint."""
        payload = await self._client.models.list()
        return extract_openai_model_ids(payload, provider_name=self._provider_name)

    @abstractmethod
    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build request body. Must be implemented by subclasses."""

    def _handle_extra_reasoning(
        self, delta: Any, sse: SSEBuilder, *, thinking_enabled: bool
    ) -> Iterator[str]:
        """Hook for provider-specific reasoning."""
        return iter(())

    def _get_retry_request_body(self, error: Exception, body: dict) -> dict | None:
        """Return a modified request body for one retry, or None."""
        return None

    def _prepare_create_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Return the body passed to the upstream OpenAI-compatible client."""
        return body

    def _apply_prompt_cache_key(self, body: dict[str, Any], request: Any) -> None:
        """Add a stable ``prompt_cache_key`` when the provider or operator opts in."""
        opted_in = (
            self.include_prompt_cache_key or self._config.include_prompt_cache_key
        )
        if not opted_in or "prompt_cache_key" in body:
            return
        key = stable_session_key(request)
        if key:
            body["prompt_cache_key"] = key

    def _record_tool_call_extra_content(
        self, tool_call_id: str, extra_content: dict[str, Any]
    ) -> None:
        """Hook for providers that must replay OpenAI tool-call metadata later."""

    def _tool_argument_aliases(self, body: dict[str, Any]) -> dict[str, dict[str, str]]:
        """Return provider-specific per-tool argument aliases for this request."""
        return {}

    async def _start_stream(self, body: dict) -> Any:
        create_body = self._prepare_create_body(body)
        if self.include_stream_usage:
            create_body = dict(create_body)
            create_body.setdefault("stream_options", {"include_usage": True})
        return await self._global_rate_limiter.execute_with_retry(
            self._client.chat.completions.create, **create_body, stream=True
        )

    def _should_disable_stream_usage(self, error: Exception) -> bool:
        """True when a 400 names ``stream_options`` as the offending parameter."""
        if not self.include_stream_usage:
            return False
        if getattr(error, "status_code", None) != 400:
            return False
        return "stream_options" in openai_error_text(error)

    async def _create_stream(self, body: dict) -> tuple[Any, dict]:
        """Create a streaming chat completion, optionally retrying once."""
        try:
            return await self._start_stream(body), body
        except Exception as error:
            if self._should_disable_stream_usage(error):
                # Sticky per-provider opt-out: later requests skip the param too.
                type(self).include_stream_usage = False
                logger.warning(
                    "{}: upstream rejected stream_options; disabling include_usage",
                    self._provider_name,
                )
                return await self._start_stream(body), body

            retry_body = self._get_retry_request_body(error, body)
            if retry_body is None:
                raise
            return await self._start_stream(retry_body), retry_body

    def _openai_error_message(self, error: Exception, request_id: str | None) -> str:
        mapped_error = map_error(error, rate_limiter=self._global_rate_limiter)
        return user_visible_message_for_mapped_provider_error(
            mapped_error,
            provider_name=self._provider_name,
            read_timeout_s=self._config.http_read_timeout,
            detail=extract_provider_error_detail(error),
            request_id=request_id,
        )

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
        thinking_enabled: bool | None = None,
    ) -> AsyncIterator[str]:
        """Stream response in Anthropic SSE format."""
        runner = OpenAIChatStreamRunner(
            self,
            request=request,
            input_tokens=input_tokens,
            request_id=request_id,
            thinking_enabled=thinking_enabled,
        )
        async for event in runner.run():
            yield event
