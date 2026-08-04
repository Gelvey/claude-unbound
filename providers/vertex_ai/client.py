"""Google Vertex AI provider using the OpenAI-compatible Chat Completions API."""

from __future__ import annotations

from typing import Any

import httpx

from providers.base import ProviderConfig
from providers.exceptions import ModelListResponseError
from providers.transports.openai_chat.google_signatures import (
    record_tool_call_extra_content,
)
from providers.transports.openai_chat.transport import OpenAIChatTransport

from .auth import GoogleAccessTokenProvider, VertexAIAuth
from .endpoint import vertex_openai_base_url, vertex_publisher_models_url
from .models import extract_vertex_model_page
from .request import build_request_body


class VertexAIProvider(OpenAIChatTransport):
    """Vertex AI Gemini models with renewable ADC and native model discovery."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        project_id: str,
        location: str = "global",
        access_token_provider: GoogleAccessTokenProvider | None = None,
        http_auth: httpx.Auth | None = None,
    ) -> None:
        self._project_id = project_id.strip()
        self._location = location.strip().lower()
        self._tool_call_extra_content_by_id: dict[str, dict[str, Any]] = {}
        self._access_token_provider = (
            access_token_provider or GoogleAccessTokenProvider(proxy=config.proxy)
        )
        if http_auth is None:
            http_auth = VertexAIAuth(self._access_token_provider, self._project_id)
        self._models_url = vertex_publisher_models_url(self._location)
        self._model_list_client = httpx.AsyncClient(
            proxy=config.proxy or None,
            timeout=httpx.Timeout(
                config.http_read_timeout,
                connect=config.http_connect_timeout,
                read=config.http_read_timeout,
                write=config.http_write_timeout,
            ),
        )
        super().__init__(
            config,
            provider_name="VERTEX_AI",
            base_url=config.base_url
            or vertex_openai_base_url(self._project_id, self._location),
            api_key=config.api_key,
            http_auth=http_auth,
        )

    async def cleanup(self) -> None:
        """Release both OpenAI-compatible and native model-list clients."""
        try:
            await super().cleanup()
        finally:
            await self._model_list_client.aclose()

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict[str, Any]:
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
            tool_call_extra_content_by_id=self._tool_call_extra_content_by_id,
        )

    def _record_tool_call_extra_content(
        self, tool_call_id: str, extra_content: dict[str, Any]
    ) -> None:
        record_tool_call_extra_content(
            self._tool_call_extra_content_by_id, tool_call_id, extra_content
        )

    async def list_model_ids(self) -> frozenset[str]:
        """List Vertex publisher models via the native API."""
        model_ids: set[str] = set()
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        while True:
            payload = await self._list_model_page(page_token)
            page_ids, page_token = extract_vertex_model_page(payload)
            model_ids.update(page_ids)
            if page_token is None:
                break
            if page_token in seen_page_tokens:
                raise ModelListResponseError(
                    "VERTEX model-list response is malformed: repeated nextPageToken"
                )
            seen_page_tokens.add(page_token)
        if not model_ids:
            raise ModelListResponseError(
                "VERTEX model-list response is malformed: response did not include "
                "any model ids"
            )
        return frozenset(model_ids)

    async def _list_model_page(self, page_token: str | None) -> Any:
        token = await self._access_token_provider.get_token()
        response = await self._model_list_client.get(
            self._models_url,
            params={"pageToken": page_token} if page_token else None,
            headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": self._project_id,
            },
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise ModelListResponseError(
                "VERTEX model-list response is malformed: invalid JSON"
            ) from exc
