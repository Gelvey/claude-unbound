"""Tests for the RAM-only OpenRouter forced-provider session override."""

from __future__ import annotations

import pytest

from core.anthropic.openrouter_session import OpenRouterSessionOverrides


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Start each case from a clean singleton so state never leaks across tests."""
    OpenRouterSessionOverrides.reset()
    yield
    OpenRouterSessionOverrides.reset()


def test_snapshot_defaults_to_unset() -> None:
    snap = OpenRouterSessionOverrides.instance().snapshot()
    assert snap == {"forced_provider": None, "allow_fallbacks": False}


def test_provider_options_returns_none_when_unset() -> None:
    assert OpenRouterSessionOverrides.instance().provider_options() is None


def test_set_then_snapshot_records_slug_and_fallback_default() -> None:
    overrides = OpenRouterSessionOverrides.instance()
    overrides.set("anthropic")
    assert overrides.snapshot() == {
        "forced_provider": "anthropic",
        "allow_fallbacks": False,
    }
    assert overrides.provider_options() == {
        "order": ["anthropic"],
        "allow_fallbacks": False,
    }


def test_set_allow_fallbacks_true_is_preserved() -> None:
    overrides = OpenRouterSessionOverrides.instance()
    overrides.set("deepinfra/turbo", allow_fallbacks=True)
    assert overrides.provider_options() == {
        "order": ["deepinfra/turbo"],
        "allow_fallbacks": True,
    }


def test_set_strips_whitespace_and_empty_clears() -> None:
    overrides = OpenRouterSessionOverrides.instance()
    overrides.set("  anthropic  ")
    assert overrides.snapshot()["forced_provider"] == "anthropic"

    overrides.set("   ")
    assert overrides.snapshot()["forced_provider"] is None
    assert overrides.provider_options() is None


def test_set_none_clears_existing_override() -> None:
    overrides = OpenRouterSessionOverrides.instance()
    overrides.set("anthropic")
    overrides.set(None)
    assert overrides.snapshot()["forced_provider"] is None
    assert overrides.provider_options() is None


def test_clear_resets_state() -> None:
    overrides = OpenRouterSessionOverrides.instance()
    overrides.set("anthropic", allow_fallbacks=True)
    overrides.clear()
    assert overrides.snapshot() == {"forced_provider": None, "allow_fallbacks": False}
    assert overrides.provider_options() is None


def test_singleton_is_shared_instance() -> None:
    """The admin endpoint and the request builder must reach the same state."""
    OpenRouterSessionOverrides.instance().set("anthropic")
    assert (
        OpenRouterSessionOverrides.instance().snapshot()["forced_provider"]
        == "anthropic"
    )


def test_reset_drops_singleton_for_fresh_start() -> None:
    OpenRouterSessionOverrides.instance().set("anthropic")
    OpenRouterSessionOverrides.reset()
    assert OpenRouterSessionOverrides.instance().snapshot() == {
        "forced_provider": None,
        "allow_fallbacks": False,
    }
