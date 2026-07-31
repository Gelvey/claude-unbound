"""Fireworks AI provider using native Anthropic-compatible Messages."""

from __future__ import annotations

from typing import Any

from providers.base import ProviderConfig
from providers.transports.anthropic_messages import AnthropicMessagesTransport

from .request import build_request_body

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


class FireworksProvider(AnthropicMessagesTransport):
    """Fireworks AI using Anthropic-compatible Messages."""

    auth_scheme = "bearer"
    anthropic_version = "2023-06-01"

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="FIREWORKS",
            default_base_url=FIREWORKS_BASE_URL,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        if thinking_enabled is None:
            thinking_enabled = self._is_thinking_enabled(request)
        return build_request_body(
            request,
            thinking_enabled=thinking_enabled,
        )
