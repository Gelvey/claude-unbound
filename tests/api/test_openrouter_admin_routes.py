"""Tests for the OpenRouter forced-provider admin API (RAM-only session override)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api import admin_routes
from api.app import create_app
from config.settings import get_settings
from core.anthropic.openrouter_session import OpenRouterSessionOverrides


def _local_client(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def _set_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def _clear_process_config(monkeypatch) -> None:
    for key in (
        "MODEL",
        "NVIDIA_NIM_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_PROXY",
        "ANTHROPIC_AUTH_TOKEN",
        "FCC_ENV_FILE",
        "HOST",
        "PORT",
        "LOG_FILE",
        "ZAI_BASE_URL",
        "CLAUDE_WORKSPACE",
        "CLAUDE_CLI_BIN",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _reset_singleton():
    OpenRouterSessionOverrides.reset()
    admin_routes._OPENROUTER_PROVIDER_CACHE["providers"] = []
    admin_routes._OPENROUTER_PROVIDER_CACHE["fetched_at"] = 0.0
    get_settings.cache_clear()
    yield
    OpenRouterSessionOverrides.reset()
    admin_routes._OPENROUTER_PROVIDER_CACHE["providers"] = []
    admin_routes._OPENROUTER_PROVIDER_CACHE["fetched_at"] = 0.0
    get_settings.cache_clear()


def _client(monkeypatch, tmp_path) -> TestClient:
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    get_settings.cache_clear()
    app = create_app(lifespan_enabled=False)
    return _local_client(app)


# ---------------------------------------------------------------------------
# GET /admin/api/openrouter/forced-provider
# ---------------------------------------------------------------------------


def test_get_forced_provider_defaults_to_unset(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.get("/admin/api/openrouter/forced-provider")
    assert response.status_code == 200
    body = response.json()
    assert body["forced_provider"] is None
    assert body["allow_fallbacks"] is False
    assert body["configured"] is False


def test_get_forced_provider_reports_configured_when_key_set(monkeypatch, tmp_path):
    # Set the key AFTER _clear_process_config (which would otherwise wipe it)
    # but BEFORE create_app builds the cached Settings instance.
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_settings.cache_clear()
    app = create_app(lifespan_enabled=False)
    client = _local_client(app)
    body = client.get("/admin/api/openrouter/forced-provider").json()
    assert body["configured"] is True


def test_get_forced_provider_is_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)
    remote = TestClient(app, client=("203.0.113.10", 50000))
    assert remote.get("/admin/api/openrouter/forced-provider").status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/api/openrouter/forced-provider
# ---------------------------------------------------------------------------


def test_post_forced_provider_sets_slug(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": "anthropic", "allow_fallbacks": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["forced_provider"] == "anthropic"
    assert body["allow_fallbacks"] is False
    # State persisted in the RAM singleton.
    assert (
        OpenRouterSessionOverrides.instance().snapshot()["forced_provider"]
        == "anthropic"
    )


def test_post_forced_provider_allow_fallbacks_persisted(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": "deepinfra/turbo", "allow_fallbacks": True},
    )
    assert response.status_code == 200
    assert response.json()["allow_fallbacks"] is True


def test_post_forced_provider_null_clears(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": "anthropic"},
    )
    response = client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": None},
    )
    assert response.status_code == 200
    assert response.json()["forced_provider"] is None
    assert OpenRouterSessionOverrides.instance().snapshot()["forced_provider"] is None


def test_post_forced_provider_empty_string_clears(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": "anthropic"},
    )
    response = client.post(
        "/admin/api/openrouter/forced-provider",
        json={"provider": "   "},
    )
    assert response.status_code == 200
    assert response.json()["forced_provider"] is None


def test_post_forced_provider_is_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)
    remote = TestClient(app, client=("203.0.113.10", 50000))
    assert (
        remote.post(
            "/admin/api/openrouter/forced-provider",
            json={"provider": "anthropic"},
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# GET /admin/api/openrouter/providers
# ---------------------------------------------------------------------------


def _providers_payload():
    return {
        "data": [
            {"slug": "anthropic", "name": "Anthropic"},
            {"slug": "deepinfra/turbo", "name": "DeepInfra Turbo"},
            {"slug": "openai", "name": "OpenAI"},
        ]
    }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient with a controllable get() and call counter."""

    def __init__(self, *args, **kwargs):
        self.get_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.get_calls += 1
        if _FakeAsyncClient._side_effect is not None:
            raise _FakeAsyncClient._side_effect
        return _FakeResponse(_FakeAsyncClient._payload)

    # Class-level config consumed by instances
    _payload = None
    _side_effect = None


def _patch_async_client(payload=None, side_effect=None):
    _FakeAsyncClient._payload = payload
    _FakeAsyncClient._side_effect = side_effect
    return patch("api.admin_routes.httpx.AsyncClient", _FakeAsyncClient)


def test_list_providers_returns_sorted_catalog(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    with _patch_async_client(payload=_providers_payload()):
        response = client.get("/admin/api/openrouter/providers")

    assert response.status_code == 200
    providers = response.json()["providers"]
    slugs = [p["slug"] for p in providers]
    assert slugs == sorted(slugs)  # sorted by name
    assert "anthropic" in slugs and "openai" in slugs


def test_list_providers_serves_cached_on_second_call(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    with _patch_async_client(payload=_providers_payload()):
        first = client.get("/admin/api/openrouter/providers")
        second = client.get("/admin/api/openrouter/providers")

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["providers"] == second.json()["providers"]


def test_list_providers_returns_502_when_upstream_fails(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    with _patch_async_client(side_effect=httpx.ConnectError("boom")):
        response = client.get("/admin/api/openrouter/providers")

    assert response.status_code == 502


def test_list_providers_is_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)
    remote = TestClient(app, client=("203.0.113.10", 50000))
    assert remote.get("/admin/api/openrouter/providers").status_code == 403
