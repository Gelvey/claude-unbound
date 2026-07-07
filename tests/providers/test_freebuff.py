"""Tests for the Freebuff2API provider."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from providers.base import ProviderConfig
from providers.freebuff.client import FreebuffProvider
from providers.freebuff.request import build_request_body

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class MockRequest:
    def __init__(self, **kwargs: Any):
        self.model = "freebuff/minimax/minimax-m2.7"
        self.messages = [MockMessage("user", "Hello")]
        self.max_tokens = 100
        self.thinking = MagicMock()
        self.thinking.type = "disabled"
        self.stream = True
        self.temperature = None
        self.top_p = None
        self.stop_sequences = None
        self.tools = []
        self.tool_choice = None
        self.metadata = None
        self.extra_body = None
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture()
def provider_config():
    return ProviderConfig(
        api_key="freebuff",
        base_url="http://127.0.0.1:8080/v1",
    )


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    @asynccontextmanager
    async def _slot():
        yield

    mock_instance = MagicMock()
    mock_instance.execute_with_retry = AsyncMock(side_effect=lambda fn, *a, **kw: fn())
    mock_instance.concurrency_slot = MagicMock(side_effect=_slot)

    with patch(
        "providers.transports.openai_chat.transport.GlobalRateLimiter"
    ) as mock_cls:
        mock_cls.get_scoped_instance.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def provider(provider_config: ProviderConfig):
    return FreebuffProvider(provider_config)


# ---------------------------------------------------------------------------
# Init tests
# ---------------------------------------------------------------------------


def test_init_sets_api_key(provider: FreebuffProvider):
    assert provider._api_key == "freebuff"


def test_init_sets_base_url(provider: FreebuffProvider):
    assert provider._base_url == "http://127.0.0.1:8080/v1"


def test_default_base_url_constant():
    from providers.defaults import FREEBUFF_DEFAULT_BASE

    assert FREEBUFF_DEFAULT_BASE == "http://127.0.0.1:8080/v1"


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080/v1"),
        ("http://127.0.0.1:8080/", "http://127.0.0.1:8080/v1"),
        ("http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1"),
        ("http://127.0.0.1:8080/v1/", "http://127.0.0.1:8080/v1"),
    ],
)
def test_normalize_freebuff_base_url(raw_url: str, expected: str) -> None:
    from providers.freebuff.client import normalize_freebuff_base_url

    assert normalize_freebuff_base_url(raw_url) == expected


def test_init_normalizes_base_url_without_v1():
    config = ProviderConfig(
        api_key="freebuff",
        base_url="http://127.0.0.1:9000",
    )
    provider = FreebuffProvider(config)
    assert provider._base_url == "http://127.0.0.1:9000/v1"


# ---------------------------------------------------------------------------
# Container detection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_detect_container_url_found(provider: FreebuffProvider):
    """Returns detected URL when container is running."""
    mock_status = {"running": True, "host_port": 38447}
    with patch(
        "providers.freebuff.client.check_container_running",
        new_callable=AsyncMock,
        return_value=mock_status,
    ):
        result = await provider._detect_container_url()
    assert result == "http://127.0.0.1:38447/v1"


@pytest.mark.asyncio()
async def test_detect_container_url_not_running(provider: FreebuffProvider):
    """Returns None when container is not running and no config file exists."""
    mock_status = {"running": False, "host_port": None}
    with (
        patch(
            "providers.freebuff.client.check_container_running",
            new_callable=AsyncMock,
            return_value=mock_status,
        ),
        patch("providers.freebuff.client.read_config_port", return_value=None),
    ):
        result = await provider._detect_container_url()
    assert result is None


@pytest.mark.asyncio()
async def test_detect_container_url_falls_back_to_config_file(
    provider: FreebuffProvider,
):
    """Returns config-file port when Docker reports no container."""
    with (
        patch(
            "providers.freebuff.client.check_container_running",
            new_callable=AsyncMock,
            return_value={"running": False, "host_port": None},
        ),
        patch(
            "providers.freebuff.client.read_config_port",
            return_value=9000,
        ),
    ):
        result = await provider._detect_container_url()
    assert result == "http://127.0.0.1:9000/v1"


@pytest.mark.asyncio()
async def test_detect_container_url_returns_none_without_source(
    provider: FreebuffProvider,
):
    """Returns None when neither Docker nor config provides a port."""
    with (
        patch(
            "providers.freebuff.client.check_container_running",
            new_callable=AsyncMock,
            return_value={"running": False, "host_port": None},
        ),
        patch(
            "providers.freebuff.client.read_config_port",
            return_value=None,
        ),
    ):
        result = await provider._detect_container_url()
    assert result is None


# ---------------------------------------------------------------------------
# Chat stream URL refresh tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_start_stream_refreshes_client_when_container_moved(
    provider: FreebuffProvider,
):
    """Rebuilding the OpenAI client when the container port changed."""
    detected_url = "http://127.0.0.1:38447/v1"
    old_client = MagicMock()
    old_client.close = AsyncMock()
    provider._client = old_client

    with (
        patch.object(
            provider,
            "_detect_container_url",
            new_callable=AsyncMock,
            return_value=detected_url,
        ),
        patch("providers.freebuff.client.AsyncOpenAI") as mock_openai_cls,
        patch("providers.freebuff.client.httpx.AsyncClient") as mock_httpx_cls,
        patch(
            "providers.transports.openai_chat.transport.OpenAIChatTransport._start_stream",
            new_callable=AsyncMock,
            return_value="stream-result",
        ) as mock_super_start,
    ):
        new_client = MagicMock()
        mock_openai_cls.return_value = new_client

        result = await provider._start_stream({"model": "freebuff/minimax/minimax-m3"})

    assert provider._base_url == detected_url
    assert result == "stream-result"
    mock_openai_cls.assert_called_once()
    assert mock_openai_cls.call_args.kwargs["base_url"] == detected_url
    assert (
        mock_openai_cls.call_args.kwargs["http_client"] is mock_httpx_cls.return_value
    )
    old_client.close.assert_awaited_once()
    mock_super_start.assert_awaited_once_with({"model": "freebuff/minimax/minimax-m3"})


@pytest.mark.asyncio()
async def test_start_stream_keeps_client_when_url_unchanged(provider: FreebuffProvider):
    """No client rebuild when the detected URL already matches."""
    old_client = MagicMock()
    old_client.close = AsyncMock()
    provider._client = old_client

    with (
        patch.object(
            provider,
            "_detect_container_url",
            new_callable=AsyncMock,
            return_value=provider._base_url,
        ),
        patch("providers.freebuff.client.AsyncOpenAI") as mock_openai_cls,
        patch("providers.freebuff.client.httpx.AsyncClient") as mock_httpx_cls,
        patch(
            "providers.transports.openai_chat.transport.OpenAIChatTransport._start_stream",
            new_callable=AsyncMock,
            return_value="stream-result",
        ) as mock_super_start,
    ):
        result = await provider._start_stream({})

    assert result == "stream-result"
    mock_openai_cls.assert_not_called()
    mock_httpx_cls.assert_not_called()
    old_client.close.assert_not_awaited()
    mock_super_start.assert_awaited_once_with({})


@pytest.mark.asyncio()
async def test_start_stream_falls_back_to_configured_url_on_connection_error(
    provider: FreebuffProvider,
):
    """Fallback to the configured URL when the detected URL is unreachable."""
    configured_url = provider._base_url
    detected_url = "http://127.0.0.1:38447/v1"
    old_client = MagicMock()
    old_client.close = AsyncMock()
    provider._client = old_client

    with (
        patch.object(
            provider,
            "_detect_container_url",
            new_callable=AsyncMock,
            return_value=detected_url,
        ),
        patch("providers.freebuff.client.AsyncOpenAI"),
        patch("providers.freebuff.client.httpx.AsyncClient"),
        patch(
            "providers.transports.openai_chat.transport.OpenAIChatTransport._start_stream",
            new_callable=AsyncMock,
            side_effect=[
                httpx.ConnectError("Connection error."),
                "stream-result",
            ],
        ) as mock_super_start,
    ):
        result = await provider._start_stream({"model": "freebuff/minimax/minimax-m3"})

    assert result == "stream-result"
    assert provider._base_url == configured_url
    assert mock_super_start.await_count == 2
    mock_super_start.assert_awaited_with({"model": "freebuff/minimax/minimax-m3"})


@pytest.mark.asyncio()
async def test_start_stream_raises_non_connection_error_immediately(
    provider: FreebuffProvider,
):
    """A non-connection error from the detected URL is not retried."""
    detected_url = "http://127.0.0.1:38447/v1"
    old_client = MagicMock()
    old_client.close = AsyncMock()
    provider._client = old_client

    with (
        patch.object(
            provider,
            "_detect_container_url",
            new_callable=AsyncMock,
            return_value=detected_url,
        ),
        patch("providers.freebuff.client.AsyncOpenAI"),
        patch("providers.freebuff.client.httpx.AsyncClient"),
        patch(
            "providers.transports.openai_chat.transport.OpenAIChatTransport._start_stream",
            new_callable=AsyncMock,
            side_effect=ValueError("bad request"),
        ) as mock_super_start,
        pytest.raises(ValueError, match="bad request"),
    ):
        await provider._start_stream({})

    assert provider._base_url == detected_url
    mock_super_start.assert_awaited_once_with({})


# ---------------------------------------------------------------------------
# Request body tests
# ---------------------------------------------------------------------------


def test_build_request_body_basic():
    request = MockRequest()
    body = build_request_body(request, thinking_enabled=False)
    assert "model" in body
    assert "messages" in body
    assert body["model"] == "freebuff/minimax/minimax-m2.7"


def test_build_request_body_thinking_disabled():
    request = MockRequest()
    body = build_request_body(request, thinking_enabled=False)
    assert "model" in body
    assert "messages" in body
    assert "extra_body" not in body


def test_build_request_body_thinking_enabled_sets_highest_reasoning():
    request = MockRequest(max_tokens=100)
    body = build_request_body(request, thinking_enabled=True)

    assert body["extra_body"]["reasoning_effort"] == "max"
    # Note: include_reasoning and chat_template_kwargs are vLLM-specific
    # and not supported by Freebuff's upstream (codebuff.com)
    assert "include_reasoning" not in body["extra_body"]
    assert "chat_template_kwargs" not in body["extra_body"]


def test_build_request_body_thinking_enabled_overrides_lower_reasoning_hints():
    request = MockRequest(
        extra_body={
            "reasoning_effort": "low",
            "include_reasoning": False,
            "chat_template_kwargs": {
                "thinking": False,
                "enable_thinking": False,
                "custom": "value",
            },
        }
    )
    body = build_request_body(request, thinking_enabled=True)

    assert body["extra_body"]["reasoning_effort"] == "max"
    # Note: include_reasoning and chat_template_kwargs are vLLM-specific
    # and not supported by Freebuff's upstream (codebuff.com), so they
    # should be removed from the request


def test_build_request_body_extra_body():
    request = MockRequest(extra_body={"custom_field": "value"})
    body = build_request_body(request, thinking_enabled=False)
    assert body["extra_body"] == {"custom_field": "value"}


def test_build_request_body_extra_body_empty():
    request = MockRequest(extra_body={})
    body = build_request_body(request, thinking_enabled=False)
    assert "extra_body" not in body


# ---------------------------------------------------------------------------
# Provider body tests
# ---------------------------------------------------------------------------


def test_build_request_body_via_provider(provider: FreebuffProvider):
    request = MockRequest()
    body = provider._build_request_body(request, thinking_enabled=False)
    assert "model" in body
    assert "messages" in body


# ---------------------------------------------------------------------------
# Cleanup test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_cleanup(provider: FreebuffProvider):
    with patch.object(provider, "_client", new_callable=MagicMock) as mock_client:
        mock_client.close = AsyncMock()
        await provider.cleanup()
        mock_client.close.assert_called_once()


def test_freebuff2api_patch_bundled():
    """The patch file is no longer needed since upstream Freebuff2API has incorporated all changes.

    The upstream repo (Gelvey/Freebuff2API commit 4597596) now includes:
    - Model-aware session routing with root agent preference
    - Model field in freeSessionResponse and cachedSession structs
    - RequestedModel parameter in session management functions
    - ensureFreebuffSystemMarker function

    If the patch file exists, it's outdated and should be removed.
    """
    from providers.freebuff.binary_manager import _PATCH_FILE

    assert not _PATCH_FILE.is_file(), (
        "Patch file should not exist - upstream Freebuff2API already has all changes. "
        "Remove the patch file to use upstream code directly."
    )
