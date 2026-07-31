"""Z.ai provider implementation (Anthropic-compatible Messages API)."""

from __future__ import annotations

from typing import Any

from providers.base import ProviderConfig
from providers.defaults import ZAI_DEFAULT_BASE
from providers.transports.anthropic_messages import AnthropicMessagesTransport

from .request import build_request_body


class ZaiProvider(AnthropicMessagesTransport):
    """Z.ai using Anthropic-compatible Messages at api.z.ai/api/anthropic/v1."""

    auth_scheme = "x-api-key"
    anthropic_version = "2023-06-01"

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="ZAI",
            default_base_url=ZAI_DEFAULT_BASE,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
        )

    def _model_list_anthropic_version(self) -> str | None:
        """Z.ai requires ``anthropic-version`` on the model-list request too."""
        return self.anthropic_version
