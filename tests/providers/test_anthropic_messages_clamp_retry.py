"""Native Anthropic transport: context-length 400 retries once with clamped max_tokens."""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.base import ProviderConfig
from providers.rate_limit import GlobalRateLimiter
from providers.transports.openai_chat import context_length_clamped_retry_body
from tests.providers.test_anthropic_messages import FakeResponse, MockRequest
from tests.providers.test_anthropic_messages import NativeProvider as _NativeProvider
from tests.stream_contract import assert_canonical_stream_error_envelope

_CLOUDFLARE_NEW_400 = (
    "Requested token count exceeds the model's maximum context length of "
    "256000 tokens. You requested a total of 256800 tokens: 224800 tokens "
    "from the input messages and 32000 tokens for the completion."
)

_OK_LINES = [
    "event: message_start",
    'data: {"type":"message_start"}',
    "",
    "event: message_stop",
    'data: {"type":"message_stop"}',
    "",
]


class ClampingProvider(_NativeProvider):
    """A native provider that opts into context-length clamping."""

    def _get_retry_request_body(self, error: Exception, body: dict) -> dict | None:
        return context_length_clamped_retry_body(error, body)


@pytest.fixture
def provider_config():
    return ProviderConfig(
        api_key="test-key",
        base_url="https://custom.test/v1/",
        rate_limit=100,
        rate_window=60,
        http_read_timeout=600.0,
        http_write_timeout=15.0,
        http_connect_timeout=5.0,
    )


def _passthrough_limiter(provider: Any) -> None:
    @asynccontextmanager
    async def _slot():
        yield

    async def _exec(fn, *args, **kwargs):
        return await fn(*args, **kwargs)

    instance = provider._global_rate_limiter
    instance.execute_with_retry = _exec
    instance.concurrency_slot = _slot
    instance.wait_if_blocked = AsyncMock(return_value=None)
    instance.set_blocked = MagicMock()


@pytest.mark.asyncio
async def test_context_length_400_retries_once_with_clamped_max_tokens(
    provider_config,
):
    """First send 400 (context-length); second 200 streams; max_tokens clamped."""
    GlobalRateLimiter.reset_instance()
    try:
        provider = ClampingProvider(provider_config)
        _passthrough_limiter(provider)
        req = MockRequest(body={"model": "test-model", "max_tokens": 32000})

        bad = FakeResponse(status_code=400, text=_CLOUDFLARE_NEW_400)
        ok = FakeResponse(lines=_OK_LINES)

        send_calls = {"n": 0}
        bodies: list[Any] = []

        def build_side_effect(*_a, **kw):
            bodies.append(kw.get("json"))
            return MagicMock()

        async def send_side_effect(*_a, **_kw):
            send_calls["n"] += 1
            return bad if send_calls["n"] == 1 else ok

        with (
            patch.object(
                provider._client, "build_request", side_effect=build_side_effect
            ),
            patch.object(
                provider._client,
                "send",
                new_callable=AsyncMock,
                side_effect=send_side_effect,
            ),
        ):
            events = [e async for e in provider.stream_response(req)]

        assert send_calls["n"] == 2
        assert bodies[0]["max_tokens"] == 32000
        assert bodies[1]["max_tokens"] == 256000 - 224800 - 64
        assert bad.is_closed
        assert ok.is_closed
        assert events == [
            "event: message_start\n",
            'data: {"type":"message_start"}\n',
            "\n",
            "event: message_stop\n",
            'data: {"type":"message_stop"}\n',
            "\n",
        ]
    finally:
        GlobalRateLimiter.reset_instance()


@pytest.mark.asyncio
async def test_context_length_400_not_retried_without_override(provider_config):
    """A provider whose hook returns None surfaces the 400 after a single send."""
    GlobalRateLimiter.reset_instance()
    try:
        provider = _NativeProvider(provider_config)
        _passthrough_limiter(provider)
        req = MockRequest(body={"model": "test-model", "max_tokens": 32000})

        bad = FakeResponse(status_code=400, text=_CLOUDFLARE_NEW_400)

        with (
            patch.object(provider._client, "build_request", return_value=MagicMock()),
            patch.object(
                provider._client,
                "send",
                new_callable=AsyncMock,
                return_value=bad,
            ) as mock_send,
        ):
            events = [e async for e in provider.stream_response(req)]

        mock_send.assert_awaited_once()
        assert bad.is_closed
        assert_canonical_stream_error_envelope(
            events, user_message_substr="Invalid request sent to provider"
        )
    finally:
        GlobalRateLimiter.reset_instance()


@pytest.mark.asyncio
async def test_context_length_400_clamp_retry_only_once(provider_config):
    """A second context-length 400 surfaces as final error (one-shot clamp)."""
    GlobalRateLimiter.reset_instance()
    try:
        provider = ClampingProvider(provider_config)
        _passthrough_limiter(provider)
        req = MockRequest(body={"model": "test-model", "max_tokens": 32000})

        bad = FakeResponse(status_code=400, text=_CLOUDFLARE_NEW_400)

        with (
            patch.object(provider._client, "build_request", return_value=MagicMock()),
            patch.object(
                provider._client,
                "send",
                new_callable=AsyncMock,
                return_value=bad,
            ) as mock_send,
        ):
            events = [e async for e in provider.stream_response(req)]

        assert mock_send.await_count == 2  # initial + one clamp retry
        assert bad.is_closed
        assert_canonical_stream_error_envelope(
            events, user_message_substr="Invalid request sent to provider"
        )
    finally:
        GlobalRateLimiter.reset_instance()
