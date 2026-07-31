"""Wafer provider implementation (native Anthropic-compatible Messages)."""

from typing import Any

from providers.base import ProviderConfig
from providers.defaults import WAFER_DEFAULT_BASE
from providers.transports.anthropic_messages import AnthropicMessagesTransport


class WaferProvider(AnthropicMessagesTransport):
    """Wafer using ``https://pass.wafer.ai/v1/messages``."""

    auth_scheme = "bearer"
    anthropic_version = "2023-06-01"

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="WAFER",
            default_base_url=WAFER_DEFAULT_BASE,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build native body; Wafer rejects omitted thinking as ``reasoning_effort=none``."""
        body = super()._build_request_body(request, thinking_enabled=thinking_enabled)
        if "thinking" not in body:
            body["thinking"] = {"type": "enabled"}
        return body
