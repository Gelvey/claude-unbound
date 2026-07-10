"""Filesystem paths for Graphify integration."""

from __future__ import annotations

from pathlib import Path

from config.paths import config_dir_path


def graphify_dir() -> Path:
    """Return the dedicated Graphify state directory under ~/.fcc."""
    return config_dir_path() / "graphify"


def graphify_venv_dir() -> Path:
    """Return the isolated Graphify venv path."""
    return graphify_dir() / "venv"


def graphify_bin_dir(venv_dir: Path | None = None) -> Path:
    """Return the venv bin directory for the platform."""
    venv = venv_dir or graphify_venv_dir()
    return venv / ("Scripts" if _is_windows() else "bin")


def projects_json_path() -> Path:
    """Return the canonical project registry path."""
    return config_dir_path() / "graphify_projects.json"


def _is_windows() -> bool:
    import sys

    return sys.platform.startswith("win")
