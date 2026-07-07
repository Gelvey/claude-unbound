"""Long-context fallback rerouting via LONG_CONTEXT_MODEL / THRESHOLD."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.responses import StreamingResponse

from api.models.anthropic import Message, MessagesRequest
from api.request_pipeline import ApiRequestPipeline
from config.settings import Settings
from providers.base import BaseProvider, ProviderConfig


class FakeProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(ProviderConfig(api_key="test"))
        self.requests: list[Any] = []

    def preflight_stream(
        self, request: Any, *, thinking_enabled: bool | None = None
    ) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    async def list_model_ids(self) -> frozenset[str]:
        return frozenset({"test-model", "big-model"})

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
        thinking_enabled: bool | None = None,
    ) -> AsyncIterator[str]:
        self.requests.append(request)
        yield "event: message_stop\ndata: {}\n\n"


async def _drain(response: StreamingResponse) -> None:
    async for _ in response.body_iterator:
        pass


def _request(model: str = "nvidia_nim/test-model") -> MessagesRequest:
    return MessagesRequest(
        model=model,
        max_tokens=100,
        messages=[Message(role="user", content="hello world")],
    )


def _settings(
    monkeypatch: pytest.MonkeyPatch, *, model: str, threshold: str
) -> Settings:
    monkeypatch.setenv("LONG_CONTEXT_MODEL", model)
    monkeypatch.setenv("LONG_CONTEXT_THRESHOLD_TOKENS", threshold)
    return Settings()


def _run(
    settings: Settings, estimated_tokens: int, *, model: str = "nvidia_nim/test-model"
) -> FakeProvider:
    provider = FakeProvider()
    pipeline = ApiRequestPipeline(
        settings,
        provider_getter=lambda _: provider,
        token_counter=lambda *_args, **_kwargs: estimated_tokens,
    )
    response = pipeline.create_message(_request(model))
    assert isinstance(response, StreamingResponse)
    asyncio.run(_drain(response))
    return provider


def test_reroutes_to_fallback_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, model="nvidia_nim/big-model", threshold="10")
    provider = _run(settings, estimated_tokens=50)
    assert provider.requests[0].model == "big-model"


def test_keeps_original_model_at_or_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, model="nvidia_nim/big-model", threshold="10")
    provider = _run(settings, estimated_tokens=10)
    assert provider.requests[0].model == "test-model"


def test_disabled_when_threshold_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, model="nvidia_nim/big-model", threshold="0")
    provider = _run(settings, estimated_tokens=10_000)
    assert provider.requests[0].model == "test-model"


def test_disabled_when_model_is_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, model="", threshold="10")
    provider = _run(settings, estimated_tokens=10_000)
    assert provider.requests[0].model == "test-model"


def test_no_reroute_when_already_on_fallback_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, model="nvidia_nim/big-model", threshold="10")
    provider = _run(settings, estimated_tokens=10_000, model="nvidia_nim/big-model")
    assert provider.requests[0].model == "big-model"


def test_invalid_fallback_ref_rejected_at_settings_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LONG_CONTEXT_MODEL", "not-a-provider-ref")
    with pytest.raises(ValueError):
        Settings()


def test_defaults_are_disabled() -> None:
    settings = Settings()
    assert settings.long_context_model == ""
    assert settings.long_context_threshold_tokens == 0
