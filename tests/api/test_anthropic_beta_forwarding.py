"""anthropic-beta header capture and forwarding to native Anthropic upstreams."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from api.model_router import ModelRouter
from api.models.anthropic import Message, MessagesRequest
from api.routes import create_message
from config.settings import Settings
from providers.base import ProviderConfig
from providers.transports.anthropic_messages import AnthropicMessagesTransport


def _messages_request() -> MessagesRequest:
    return MessagesRequest(
        model="nvidia_nim/test-model",
        max_tokens=100,
        messages=[Message(role="user", content="hi")],
    )


def _http_request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "query_string": b"",
            "headers": headers,
        }
    )


class TestRouteCapture:
    @pytest.mark.asyncio
    async def test_route_captures_header_into_private_attr(self) -> None:
        request_data = _messages_request()
        pipeline = MagicMock()
        await create_message(
            _http_request(
                [(b"anthropic-beta", b"fine-grained-tool-streaming-2025-05-14")]
            ),
            request_data,
            pipeline=pipeline,
            settings=Settings(),
            _auth=None,
        )
        assert request_data._anthropic_beta == "fine-grained-tool-streaming-2025-05-14"
        pipeline.create_message.assert_called_once_with(request_data)

    @pytest.mark.asyncio
    async def test_route_leaves_attr_none_without_header(self) -> None:
        request_data = _messages_request()
        await create_message(
            _http_request([]),
            request_data,
            pipeline=MagicMock(),
            settings=Settings(),
            _auth=None,
        )
        assert request_data._anthropic_beta is None

    @pytest.mark.asyncio
    async def test_forwarding_disabled_skips_capture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FORWARD_ANTHROPIC_BETA", "false")
        request_data = _messages_request()
        await create_message(
            _http_request([(b"anthropic-beta", b"some-beta")]),
            request_data,
            pipeline=MagicMock(),
            settings=Settings(),
            _auth=None,
        )
        assert request_data._anthropic_beta is None


class TestPrivateAttrPropagation:
    def test_private_attr_survives_deep_model_copy(self) -> None:
        request = _messages_request()
        request._anthropic_beta = "beta-token"
        copied = request.model_copy(deep=True)
        assert copied._anthropic_beta == "beta-token"

    def test_private_attr_survives_model_router_resolution(self) -> None:
        request = _messages_request()
        request._anthropic_beta = "beta-token"
        routed = ModelRouter(Settings()).resolve_messages_request(request)
        assert routed.request._anthropic_beta == "beta-token"

    def test_private_attr_excluded_from_serialization(self) -> None:
        request = _messages_request()
        request._anthropic_beta = "beta-token"
        assert "beta-token" not in str(request.model_dump())


class TestTransportHeaderMerge:
    def _transport(self) -> AnthropicMessagesTransport:
        return AnthropicMessagesTransport(
            ProviderConfig(api_key="k"),
            provider_name="TEST",
            default_base_url="http://localhost:9",
        )

    def test_merged_headers_layer_extras_over_base(self) -> None:
        transport = self._transport()
        headers = transport._merged_request_headers({"anthropic-beta": "b1"})
        assert headers["anthropic-beta"] == "b1"
        assert headers["Content-Type"] == "application/json"

    def test_merged_headers_without_extras_are_base_only(self) -> None:
        transport = self._transport()
        assert transport._merged_request_headers(None) == {
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_send_stream_request_passes_extra_headers(self) -> None:
        transport = self._transport()
        client = MagicMock()
        client.build_request = MagicMock(return_value="built")
        client.send = AsyncMock(return_value="response")
        transport._client = client

        result = await transport._send_stream_request(
            {"model": "m"}, extra_headers={"anthropic-beta": "beta-token"}
        )

        assert result == "response"
        headers = client.build_request.call_args.kwargs["headers"]
        assert headers["anthropic-beta"] == "beta-token"
        client.send.assert_awaited_once_with("built", stream=True)

    @pytest.mark.asyncio
    async def test_send_stream_request_defaults_to_base_headers(self) -> None:
        transport = self._transport()
        client = MagicMock()
        client.build_request = MagicMock(return_value="built")
        client.send = AsyncMock(return_value="response")
        transport._client = client

        await transport._send_stream_request({"model": "m"})

        headers = client.build_request.call_args.kwargs["headers"]
        assert "anthropic-beta" not in headers


def test_forward_anthropic_beta_defaults_on() -> None:
    assert Settings().forward_anthropic_beta is True
