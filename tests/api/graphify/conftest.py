"""Fixtures for Graphify tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def graphify_tmp_home(monkeypatch, tmp_path: Path) -> Path:
    """Redirect ~/.fcc and HOME to a temporary directory for the test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr("config.paths.config_dir_path", lambda: home / ".fcc")
    return home


@pytest.fixture
def graphify_settings():
    """Return Settings with Graphify enabled and deterministic values."""
    from config.settings import Settings

    return Settings.model_construct(
        graphify_enabled=True,
        graphify_server_port=0,
        graphify_python_path="",
        graphify_api_key="secret-key",
        graphify_auto_index_on_start=False,
        anthropic_auth_token="",
    )
