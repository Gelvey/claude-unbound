"""Tests for the gateway model-id encoding and 1M context-window marker."""

from api.gateway_model_ids import (
    decode_gateway_model_id,
    gateway_model_id,
    no_thinking_gateway_model_id,
    strip_context_window_marker,
)


def test_gateway_model_id_appends_1m_marker():
    assert gateway_model_id("cloudflare_ai/deepseek-v4-pro-0813") == (
        "anthropic/cloudflare_ai/deepseek-v4-pro-0813"
    )
    assert (
        gateway_model_id("cloudflare_ai/deepseek-v4-pro-0813", context_window_1m=True)
        == "anthropic/cloudflare_ai/deepseek-v4-pro-0813[1m]"
    )


def test_no_thinking_gateway_model_id_appends_1m_marker():
    assert (
        no_thinking_gateway_model_id(
            "cloudflare_ai/deepseek-v4-pro-0813", context_window_1m=True
        )
        == "claude-3-freecc-no-thinking/cloudflare_ai/deepseek-v4-pro-0813[1m]"
    )


def test_strip_context_window_marker():
    assert strip_context_window_marker("deepseek-v4-pro-0813[1m]") == (
        "deepseek-v4-pro-0813"
    )
    assert strip_context_window_marker("deepseek-v4-pro-0813[1M]") == (
        "deepseek-v4-pro-0813"
    )
    assert strip_context_window_marker("deepseek-v4-pro-0813") == (
        "deepseek-v4-pro-0813"
    )
    assert strip_context_window_marker("") == ""


def test_decode_gateway_model_id_strips_1m_marker():
    decoded = decode_gateway_model_id(
        "anthropic/cloudflare_ai/deepseek-v4-pro-0813[1m]"
    )
    assert decoded is not None
    assert decoded.provider_id == "cloudflare_ai"
    assert decoded.provider_model == "deepseek-v4-pro-0813"
    assert decoded.force_thinking_enabled is None


def test_decode_gateway_model_id_strips_1m_marker_no_thinking():
    decoded = decode_gateway_model_id(
        "claude-3-freecc-no-thinking/cloudflare_ai/deepseek-v4-pro-0813[1m]"
    )
    assert decoded is not None
    assert decoded.provider_model == "deepseek-v4-pro-0813"
    assert decoded.force_thinking_enabled is False


def test_gateway_model_id_handles_nested_slashes_in_provider_model():
    ref = "cloudflare_ai/@cf/deepseek-ai/deepseek-v4-pro-0813"
    model_id = gateway_model_id(ref, context_window_1m=True)
    assert model_id == (
        "anthropic/cloudflare_ai/@cf/deepseek-ai/deepseek-v4-pro-0813[1m]"
    )

    decoded = decode_gateway_model_id(model_id)
    assert decoded is not None
    assert decoded.provider_id == "cloudflare_ai"
    assert decoded.provider_model == "@cf/deepseek-ai/deepseek-v4-pro-0813"
    assert decoded.force_thinking_enabled is None
