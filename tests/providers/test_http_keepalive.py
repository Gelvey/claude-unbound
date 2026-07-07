"""HTTP keep-alive: provider transports must not use httpx's 5s default expiry."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import httpx
import pytest

from config.constants import HTTP_KEEPALIVE_EXPIRY_DEFAULT, HTTP_MIN_POOL_SIZE
from providers.base import (
    ProviderConfig,
    provider_http_limits,
    provider_http_timeout,
)
from providers.transports.anthropic_messages import AnthropicMessagesTransport
from providers.transports.openai_chat import OpenAIChatTransport


class _ChatProvider(OpenAIChatTransport):
    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="TEST_CHAT",
            base_url="https://example.test/v1",
            api_key=config.api_key,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        return {}


class _NativeProvider(AnthropicMessagesTransport):
    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="TEST_NATIVE",
            default_base_url="https://example.test/v1",
        )

    def _request_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}


def _config(**overrides: Any) -> ProviderConfig:
    return ProviderConfig(api_key="test-key", **overrides)


class TestProviderHttpLimits:
    def test_keepalive_expiry_is_long(self) -> None:
        limits = provider_http_limits(_config())
        assert limits.keepalive_expiry == HTTP_KEEPALIVE_EXPIRY_DEFAULT
        assert HTTP_KEEPALIVE_EXPIRY_DEFAULT >= 600.0

    def test_pool_size_floor(self) -> None:
        limits = provider_http_limits(_config(max_concurrency=1))
        assert limits.max_connections == HTTP_MIN_POOL_SIZE
        assert limits.max_keepalive_connections == HTTP_MIN_POOL_SIZE

    def test_pool_size_scales_with_concurrency(self) -> None:
        limits = provider_http_limits(_config(max_concurrency=10))
        assert limits.max_connections == 40
        assert limits.max_keepalive_connections == 40


class TestProviderHttpTimeout:
    def test_timeout_uses_config_values(self) -> None:
        config = _config(
            http_read_timeout=123.0,
            http_write_timeout=7.0,
            http_connect_timeout=3.0,
        )
        timeout = provider_http_timeout(config)
        assert timeout.read == 123.0
        assert timeout.write == 7.0
        assert timeout.connect == 3.0


class _SpyAsyncClient(httpx.AsyncClient):
    """Real AsyncClient subclass that records constructor kwargs."""

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **kwargs: Any):
        type(self).calls.append(kwargs)
        super().__init__(**kwargs)


@pytest.fixture()
def _spy_async_client():
    _SpyAsyncClient.calls = []
    with patch(
        "providers.transports.openai_chat.transport.httpx.AsyncClient",
        _SpyAsyncClient,
    ):
        yield _SpyAsyncClient


class TestOpenAIChatTransportKeepAlive:
    @pytest.mark.asyncio
    async def test_explicit_client_with_keepalive_limits(
        self, _spy_async_client: type[_SpyAsyncClient]
    ) -> None:
        provider = _ChatProvider(_config())
        assert len(_spy_async_client.calls) == 1
        kwargs = _spy_async_client.calls[0]
        assert kwargs["limits"].keepalive_expiry == HTTP_KEEPALIVE_EXPIRY_DEFAULT
        assert kwargs["proxy"] is None
        await provider.cleanup()

    @pytest.mark.asyncio
    async def test_proxy_still_applied(
        self, _spy_async_client: type[_SpyAsyncClient]
    ) -> None:
        provider = _ChatProvider(_config(proxy="http://proxy.test:8080"))
        kwargs = _spy_async_client.calls[0]
        assert kwargs["proxy"] == "http://proxy.test:8080"
        assert kwargs["limits"].keepalive_expiry == HTTP_KEEPALIVE_EXPIRY_DEFAULT
        await provider.cleanup()


class TestAnthropicMessagesTransportKeepAlive:
    @pytest.mark.asyncio
    async def test_client_created_with_keepalive_limits(self) -> None:
        with patch(
            "providers.transports.anthropic_messages.transport.httpx.AsyncClient",
            wraps=httpx.AsyncClient,
        ) as spy:
            provider = _NativeProvider(_config())
        assert spy.call_count == 1
        limits = spy.call_args.kwargs["limits"]
        assert limits.keepalive_expiry == HTTP_KEEPALIVE_EXPIRY_DEFAULT
        assert limits.max_connections >= HTTP_MIN_POOL_SIZE
        await provider.cleanup()
