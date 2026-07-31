"""Cerebras Inference provider (OpenAI-compatible chat completions)."""

from providers.base import ProviderConfig
from providers.defaults import CEREBRAS_DEFAULT_BASE
from providers.transports.openai_chat import GenericOpenAIChatProvider

from .request import build_request_body


class CerebrasProvider(GenericOpenAIChatProvider):
    """Cerebras API at ``https://api.cerebras.ai/v1/chat/completions``."""

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="CEREBRAS",
            base_url=config.base_url or CEREBRAS_DEFAULT_BASE,
            api_key=config.api_key,
            request_builder=build_request_body,
        )
