"""Provider usage extraction and stream_options include_usage behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import openai
import pytest
from httpx import Request, Response

from providers.base import ProviderConfig
from providers.cloudflare_ai.client import CloudflareAiProvider
from providers.transports.openai_chat.usage import (
    ProviderStreamUsage,
    extract_provider_stream_usage,
)


class TestExtractProviderStreamUsage:
    def test_openai_shape_with_cached_tokens(self) -> None:
        usage_info = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=50,
            prompt_tokens_details=SimpleNamespace(cached_tokens=800),
        )
        usage = extract_provider_stream_usage(usage_info)
        assert usage.prompt_tokens == 1000
        assert usage.output_tokens == 50
        assert usage.cache_read_input_tokens == 800
        assert usage.anthropic_input_tokens == 200

    def test_deepseek_shape(self) -> None:
        usage_info = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=20,
            prompt_tokens_details=None,
            prompt_cache_hit_tokens=900,
            prompt_cache_miss_tokens=100,
        )
        usage = extract_provider_stream_usage(usage_info)
        assert usage.cache_read_input_tokens == 900
        assert usage.anthropic_input_tokens == 100

    def test_mapping_shape(self) -> None:
        usage = extract_provider_stream_usage(
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 4},
            }
        )
        assert usage.prompt_tokens == 10
        assert usage.output_tokens == 5
        assert usage.cache_read_input_tokens == 4
        assert usage.anthropic_input_tokens == 6

    def test_no_cache_details(self) -> None:
        usage = extract_provider_stream_usage(
            SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        )
        assert usage.cache_read_input_tokens is None
        assert usage.anthropic_input_tokens == 10

    def test_none_usage(self) -> None:
        usage = extract_provider_stream_usage(None)
        assert usage == ProviderStreamUsage()
        assert usage.anthropic_input_tokens is None

    def test_zero_cached_tokens_treated_as_no_cache(self) -> None:
        usage = extract_provider_stream_usage(
            SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=1,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            )
        )
        assert usage.cache_read_input_tokens is None

    def test_cached_exceeding_prompt_clamps_to_zero_input(self) -> None:
        usage = ProviderStreamUsage(
            prompt_tokens=10, output_tokens=1, cache_read_input_tokens=99
        )
        assert usage.anthropic_input_tokens == 0


def _provider() -> CloudflareAiProvider:
    return CloudflareAiProvider(
        ProviderConfig(api_key="k", base_url="http://localhost/ai/v1")
    )


def _bad_request(message: str) -> openai.BadRequestError:
    response = Response(status_code=400, request=Request("POST", "http://test"))
    return openai.BadRequestError(
        message, response=response, body={"error": {"message": message}}
    )


class TestStreamOptionsIncludeUsage:
    @pytest.fixture(autouse=True)
    def _reset_include_stream_usage(self):
        yield
        # Sticky opt-out mutates the provider class; restore for other tests.
        for cls in (CloudflareAiProvider,):
            if "include_stream_usage" in cls.__dict__:
                del cls.include_stream_usage

    @pytest.mark.asyncio
    async def test_stream_options_added_by_default(self) -> None:
        provider = _provider()
        calls: list[dict[str, Any]] = []

        async def fake_execute(_fn, **kwargs):
            calls.append(kwargs)
            return "stream"

        with patch.object(
            provider._global_rate_limiter, "execute_with_retry", fake_execute
        ):
            stream, body = await provider._create_stream({"model": "m"})
        assert stream == "stream"
        assert calls[0]["stream_options"] == {"include_usage": True}
        assert calls[0]["stream"] is True
        # Original body is not mutated.
        assert body == {"model": "m"}

    @pytest.mark.asyncio
    async def test_stream_options_preserves_caller_value(self) -> None:
        provider = _provider()
        calls: list[dict[str, Any]] = []

        async def fake_execute(_fn, **kwargs):
            calls.append(kwargs)
            return "stream"

        with patch.object(
            provider._global_rate_limiter, "execute_with_retry", fake_execute
        ):
            await provider._create_stream(
                {"model": "m", "stream_options": {"include_usage": False}}
            )
        assert calls[0]["stream_options"] == {"include_usage": False}

    @pytest.mark.asyncio
    async def test_stream_options_400_disables_and_retries_without(self) -> None:
        provider = _provider()
        error = _bad_request("Unknown parameter: 'stream_options'.")
        calls: list[dict[str, Any]] = []

        async def fake_execute(_fn, **kwargs):
            calls.append(kwargs)
            if "stream_options" in kwargs:
                raise error
            return "stream"

        with patch.object(
            provider._global_rate_limiter, "execute_with_retry", fake_execute
        ):
            stream, _body = await provider._create_stream({"model": "m"})

        assert stream == "stream"
        assert len(calls) == 2
        assert "stream_options" in calls[0]
        assert "stream_options" not in calls[1]
        assert provider.include_stream_usage is False

        # Subsequent requests skip the parameter entirely.
        calls.clear()
        with patch.object(
            provider._global_rate_limiter, "execute_with_retry", fake_execute
        ):
            await provider._create_stream({"model": "m"})
        assert len(calls) == 1
        assert "stream_options" not in calls[0]

    @pytest.mark.asyncio
    async def test_unrelated_400_still_raises(self) -> None:
        provider = _provider()
        error = _bad_request("invalid tool schema")

        async def fake_execute(_fn, **_kwargs):
            raise error

        with (
            patch.object(
                provider._global_rate_limiter, "execute_with_retry", fake_execute
            ),
            pytest.raises(openai.BadRequestError),
        ):
            await provider._create_stream({"model": "m"})
        assert provider.include_stream_usage is True
