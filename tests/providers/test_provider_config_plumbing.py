"""Settings -> ProviderConfig plumbing for prompt_cache_key and HTTP/2."""

from __future__ import annotations

from typing import Any, cast

import pytest

from api.models.anthropic import MessagesRequest
from config.provider_catalog import PROVIDER_CATALOG
from config.settings import Settings
from core.anthropic.session_key import stable_session_key
from providers.base import ProviderConfig
from providers.registry import build_provider_config


def _request(**overrides: Any) -> MessagesRequest:
    payload: dict[str, Any] = {
        "model": "test-model",
        "max_tokens": 100,
        "system": "You are helpful.",
        "messages": [{"role": "user", "content": "hello"}],
    }
    payload.update(overrides)
    return MessagesRequest.model_validate(payload)


class TestPromptCacheKeyProviderSet:
    def test_empty_by_default(self) -> None:
        assert Settings().prompt_cache_key_provider_set() == frozenset()

    def test_parses_comma_separated_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROMPT_CACHE_KEY_PROVIDERS", " nvidia_nim, Groq ,")
        assert Settings().prompt_cache_key_provider_set() == frozenset(
            {"nvidia_nim", "groq"}
        )


class TestBuildProviderConfigPlumbing:
    def test_defaults_off(self) -> None:
        config = build_provider_config(PROVIDER_CATALOG["nvidia_nim"], Settings())
        assert config.include_prompt_cache_key is False
        assert config.http2 is False

    def test_listed_provider_opts_into_prompt_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROMPT_CACHE_KEY_PROVIDERS", "nvidia_nim")
        config = build_provider_config(PROVIDER_CATALOG["nvidia_nim"], Settings())
        assert config.include_prompt_cache_key is True

    def test_unlisted_provider_stays_opted_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROMPT_CACHE_KEY_PROVIDERS", "groq")
        config = build_provider_config(PROVIDER_CATALOG["nvidia_nim"], Settings())
        assert config.include_prompt_cache_key is False

    def test_http2_plumbed_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROVIDER_HTTP2", "true")
        config = build_provider_config(PROVIDER_CATALOG["nvidia_nim"], Settings())
        assert config.http2 is True


class TestApplyPromptCacheKeyConfigFlag:
    def _provider(self, *, include_prompt_cache_key: bool):
        from providers.cloudflare_ai.client import CloudflareAiProvider

        return CloudflareAiProvider(
            ProviderConfig(
                api_key="k",
                base_url="http://localhost/ai/v1",
                include_prompt_cache_key=include_prompt_cache_key,
            )
        )

    def test_config_flag_opts_in(self) -> None:
        provider = self._provider(include_prompt_cache_key=True)
        assert provider.include_prompt_cache_key is False  # class attr untouched
        request = _request(metadata={"user_id": "user-abc"})
        body: dict = {"model": "m"}
        provider._apply_prompt_cache_key(body, request)
        assert body["prompt_cache_key"] == stable_session_key(request)

    def test_config_flag_off_keeps_body_unchanged(self) -> None:
        provider = self._provider(include_prompt_cache_key=False)
        body: dict = {"model": "m"}
        provider._apply_prompt_cache_key(body, _request())
        assert "prompt_cache_key" not in body


class TestHttp2ClientPlumbing:
    def test_openai_chat_transport_enables_http2(self) -> None:
        from providers.cloudflare_ai.client import CloudflareAiProvider

        provider = CloudflareAiProvider(
            ProviderConfig(api_key="k", base_url="http://localhost/ai/v1", http2=True)
        )
        # httpx enables the h2 transport lazily; the flag lives on the pool
        # (private httpx internals, hence the Any cast).
        assert cast(Any, provider._http_client._transport)._pool._http2 is True

    def test_anthropic_messages_transport_enables_http2(self) -> None:
        from providers.transports.anthropic_messages import AnthropicMessagesTransport

        transport = AnthropicMessagesTransport(
            ProviderConfig(api_key="k", http2=True),
            provider_name="TEST",
            default_base_url="http://localhost:9",
        )
        assert cast(Any, transport._client._transport)._pool._http2 is True
