"""Tests for provider configuration status classification."""

from __future__ import annotations

from api.admin_status import provider_config_status


def _state(values: dict[str, str]) -> dict[str, dict[str, str]]:
    return {key: {"value": val, "source": "test"} for key, val in values.items()}


def _status_for(statuses: list[dict], provider_id: str) -> dict:
    for entry in statuses:
        if entry["provider_id"] == provider_id:
            return entry
    raise AssertionError(f"no status for {provider_id}")


def test_vertex_ai_configured_when_project_id_set():
    statuses = provider_config_status(_state({"VERTEX_AI_PROJECT_ID": "my-project"}))
    entry = _status_for(statuses, "vertex_ai")
    assert entry["kind"] == "remote"
    assert entry["status"] == "configured"
    assert entry["label"] == "Configured"


def test_vertex_ai_partial_when_project_id_missing():
    statuses = provider_config_status(_state({"VERTEX_AI_PROJECT_ID": ""}))
    entry = _status_for(statuses, "vertex_ai")
    assert entry["kind"] == "remote"
    assert entry["status"] == "partial"
    assert "VERTEX_AI_PROJECT_ID" in entry["label"]
    assert entry["missing_envs"] == ["VERTEX_AI_PROJECT_ID"]


def test_vertex_ai_not_classified_as_local():
    """Regression: Vertex must never show 'Missing URL' — its URL is composed."""
    statuses = provider_config_status(_state({"VERTEX_AI_PROJECT_ID": "my-project"}))
    entry = _status_for(statuses, "vertex_ai")
    assert entry["kind"] != "local"
    assert entry["status"] != "missing_url"


def test_local_provider_still_requires_url():
    statuses = provider_config_status(_state({"LM_STUDIO_BASE_URL": ""}))
    entry = _status_for(statuses, "lmstudio")
    assert entry["kind"] == "local"
    assert entry["status"] == "missing_url"


def test_remote_apikey_provider_configured_when_key_set():
    statuses = provider_config_status(_state({"GEMINI_API_KEY": "ai-studio-key"}))
    entry = _status_for(statuses, "gemini")
    assert entry["kind"] == "remote"
    assert entry["status"] == "configured"


def test_cloudflare_partial_without_account_id():
    statuses = provider_config_status(_state({"CLOUDFLARE_AI_API_KEY": "cf-key"}))
    entry = _status_for(statuses, "cloudflare_ai")
    assert entry["kind"] == "remote"
    assert entry["status"] == "partial"
    assert "CLOUDFLARE_AI_ACCOUNT_ID" in entry["label"]
