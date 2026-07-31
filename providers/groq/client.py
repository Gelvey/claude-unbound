"""Groq provider implementation (OpenAI-compatible chat completions)."""

from providers.base import ProviderConfig
from providers.defaults import GROQ_DEFAULT_BASE
from providers.transports.openai_chat import GenericOpenAIChatProvider

from .request import build_request_body


class GroqProvider(GenericOpenAIChatProvider):
    """Groq API using ``https://api.groq.com/openai/v1/chat/completions``."""

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="GROQ",
            base_url=config.base_url or GROQ_DEFAULT_BASE,
            api_key=config.api_key,
            request_builder=build_request_body,
        )
