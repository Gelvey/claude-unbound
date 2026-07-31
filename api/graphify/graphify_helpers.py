"""Venv management and filesystem helper functions for the Graphify manager.

Extracted from ``manager.py`` — pure module-level functions with no class-state
dependency.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

from loguru import logger

from .graphify_probes import _GRAPHIFY_PACKAGE


def _is_module_importable(python: str, module: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError, OSError:
        return False
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def _is_graphify_importable(python: str) -> bool:
    return _is_module_importable(python, "graphify")


def _pip_path(python: str) -> str:
    """Return the pip executable sitting next to *python* in a venv."""
    return str(
        Path(python).parent / ("pip.exe" if sys.platform.startswith("win") else "pip")
    )


def _venv_python_path(venv_dir: Path) -> str:
    bin_dir = venv_dir / ("Scripts" if sys.platform.startswith("win") else "bin")
    exe = "python.exe" if sys.platform.startswith("win") else "python"
    return str(bin_dir / exe)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _directory_size(path: Path) -> int:
    """Return the total byte size of *path*, following directories recursively."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                total += _directory_size(Path(entry.path))
            else:
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def _format_bytes(n: int) -> str:
    """Return a human-readable size string for *n* bytes."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


async def _ensure_graphify_venv(venv_dir: Path) -> str:
    """Create an isolated venv and install ``graphifyy[mcp]`` if missing."""
    python = _venv_python_path(venv_dir)
    if _is_graphify_importable(python):
        return python

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    logger.info("GRAPHIFY_MANAGER: creating isolated venv at {}", venv_dir)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "venv",
        str(venv_dir),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        decoded = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to create Graphify venv: {decoded}")

    pip = _pip_path(python)
    logger.info("GRAPHIFY_MANAGER: installing {} into isolated venv", _GRAPHIFY_PACKAGE)
    proc = await asyncio.create_subprocess_exec(
        pip,
        "install",
        "--quiet",
        _GRAPHIFY_PACKAGE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to install graphifyy: {stderr.decode('utf-8', errors='replace')}"
        )

    return python
