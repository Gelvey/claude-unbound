"""Settings parsing tests for the Graphify config block."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings


@pytest.mark.parametrize(
    "env_vars, expected",
    [
        ({}, {"graphify_enabled": False, "graphify_server_port": 7120}),
        (
            {"GRAPHIFY_ENABLED": "true", "GRAPHIFY_SERVER_PORT": "8765"},
            {"graphify_enabled": True, "graphify_server_port": 8765},
        ),
        (
            {
                "GRAPHIFY_PYTHON_PATH": "/usr/bin/python3",
                "GRAPHIFY_API_KEY": "secret",
                "GRAPHIFY_AUTO_INDEX_ON_START": "1",
            },
            {
                "graphify_python_path": "/usr/bin/python3",
                "graphify_api_key": "secret",
                "graphify_auto_index_on_start": True,
            },
        ),
        (
            {
                "GRAPHIFY_LLM_BACKEND": "ollama",
                "GRAPHIFY_LLM_API_KEY": "dummy",
            },
            {
                "graphify_llm_backend": "ollama",
                "graphify_llm_api_key": "dummy",
            },
        ),
        (
            {
                "GRAPHIFY_LLM_BACKEND": "cloudflare",
                "GRAPHIFY_LLM_MODEL": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "GRAPHIFY_CODE_ONLY": "true",
            },
            {
                "graphify_llm_backend": "cloudflare",
                "graphify_llm_model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "graphify_code_only": True,
            },
        ),
        (
            {
                "GRAPHIFY_LLM_BACKEND": "lmstudio",
                "GRAPHIFY_LLM_MODEL": "qwen2.5-coder-7b-instruct",
            },
            {
                "graphify_llm_backend": "lmstudio",
                "graphify_llm_model": "qwen2.5-coder-7b-instruct",
            },
        ),
    ],
)
def test_graphify_settings_parsing(
    env_vars: dict[str, str],
    expected: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in {
        "GRAPHIFY_ENABLED",
        "GRAPHIFY_SERVER_PORT",
        "GRAPHIFY_PYTHON_PATH",
        "GRAPHIFY_API_KEY",
        "GRAPHIFY_LLM_BACKEND",
        "GRAPHIFY_LLM_API_KEY",
        "GRAPHIFY_LLM_MODEL",
        "GRAPHIFY_CODE_ONLY",
        "GRAPHIFY_AUTO_INDEX_ON_START",
    }:
        monkeypatch.delenv(key, raising=False)
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    settings = Settings()
    for key, value in expected.items():
        assert getattr(settings, key) == value


@pytest.mark.parametrize(
    "env_value, expected",
    [
        (None, True),  # unset -> default True (stateless required for Claude Code)
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),  # opt-in to stateful session manager
        ("False", False),
        ("0", False),
        ("no", False),
    ],
)
def test_graphify_stateless_setting_parses_env(
    env_value: str | None,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """GRAPHIFY_STATELESS controls whether the graphify HTTP transport requires
    an mcp-session-id header. Stateless is the default so that Claude Code's
    StreamableHTTPClientTransport works regardless of session-cache state.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GRAPHIFY_STATELESS", raising=False)
    if env_value is not None:
        monkeypatch.setenv("GRAPHIFY_STATELESS", env_value)

    settings = Settings()
    assert settings.graphify_stateless is expected


def test_graphify_llm_fields_default_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in {
        "GRAPHIFY_LLM_BACKEND",
        "GRAPHIFY_LLM_API_KEY",
        "GRAPHIFY_LLM_MODEL",
        "GRAPHIFY_CODE_ONLY",
    }:
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.graphify_llm_backend == ""
    assert settings.graphify_llm_api_key == ""
    assert settings.graphify_llm_model == ""
    assert settings.graphify_code_only is False
