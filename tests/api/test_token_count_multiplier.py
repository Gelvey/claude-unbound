"""TOKEN_COUNT_MULTIPLIER applied only to /v1/messages/count_tokens."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.models.anthropic import Message, TokenCountRequest
from api.request_pipeline import ApiRequestPipeline
from config.settings import Settings


def _pipeline(settings: Settings, raw_tokens: int) -> ApiRequestPipeline:
    return ApiRequestPipeline(
        settings,
        provider_getter=MagicMock(),
        token_counter=lambda *_args, **_kwargs: raw_tokens,
    )


def _count_request() -> TokenCountRequest:
    return TokenCountRequest(
        model="nvidia_nim/test-model",
        messages=[Message(role="user", content="hello")],
    )


def test_default_multiplier_is_1_15() -> None:
    assert Settings().token_count_multiplier == 1.15


def test_count_tokens_applies_default_multiplier() -> None:
    settings = Settings()
    response = _pipeline(settings, raw_tokens=100).count_tokens(_count_request())
    # int() matches production truncation (100 * 1.15 is 114.999... in floats).
    assert response.input_tokens == int(100 * settings.token_count_multiplier)
    assert response.input_tokens > 100


def test_multiplier_1_0_is_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_COUNT_MULTIPLIER", "1.0")
    response = _pipeline(Settings(), raw_tokens=100).count_tokens(_count_request())
    assert response.input_tokens == 100


def test_count_tokens_floors_at_one_token() -> None:
    response = _pipeline(Settings(), raw_tokens=0).count_tokens(_count_request())
    assert response.input_tokens == 1


def test_streamed_input_tokens_are_not_multiplied() -> None:
    """The multiplier must not leak into the provider-stream token estimate."""
    from collections.abc import AsyncIterator
    from typing import Any

    from api.models.anthropic import MessagesRequest
    from providers.base import BaseProvider, ProviderConfig

    class FakeProvider(BaseProvider):
        def __init__(self) -> None:
            super().__init__(ProviderConfig(api_key="test"))
            self.stream_kwargs: list[dict[str, Any]] = []

        def preflight_stream(
            self, request: Any, *, thinking_enabled: bool | None = None
        ) -> None:
            return None

        async def cleanup(self) -> None:
            return None

        async def list_model_ids(self) -> frozenset[str]:
            return frozenset({"test-model"})

        async def stream_response(
            self,
            request: Any,
            input_tokens: int = 0,
            *,
            request_id: str | None = None,
            thinking_enabled: bool | None = None,
        ) -> AsyncIterator[str]:
            self.stream_kwargs.append({"input_tokens": input_tokens})
            yield "event: message_stop\ndata: {}\n\n"

    import asyncio

    from fastapi.responses import StreamingResponse

    provider = FakeProvider()
    pipeline = ApiRequestPipeline(
        Settings(),
        provider_getter=lambda _: provider,
        token_counter=lambda *_args, **_kwargs: 100,
    )
    response = pipeline.create_message(
        MessagesRequest(
            model="nvidia_nim/test-model",
            max_tokens=50,
            messages=[Message(role="user", content="hi")],
        )
    )
    assert isinstance(response, StreamingResponse)

    async def _drain() -> None:
        async for _ in response.body_iterator:
            pass

    asyncio.run(_drain())
    assert provider.stream_kwargs[0]["input_tokens"] == 100  # raw, no 1.15x
