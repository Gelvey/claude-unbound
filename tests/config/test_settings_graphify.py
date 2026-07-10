"""Settings parsing tests for the Graphify config block."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings


@pytest.mark.parametrize(
    "env_vars, expected",
    [
        ({}, {"graphify_enabled": False, "graphify_server_port": 0}),
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
        "GRAPHIFY_AUTO_INDEX_ON_START",
    }:
        monkeypatch.delenv(key, raising=False)
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    settings = Settings()
    for key, value in expected.items():
        assert getattr(settings, key) == value
