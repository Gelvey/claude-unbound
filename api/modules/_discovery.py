"""Shared helpers for discovering and importing custom modules.

The server (api/modules/loader.py) and the CLI (cli/module_cli.py) both need
to walk the modules directory and import files/packages from arbitrary paths.
Keeping the discovery logic in one place keeps the two loaders consistent.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

_MODULE_FILE_PREFIX = "claude_unbound_module_"
_CLI_MODULE_FILE_PREFIX = "claude_unbound_cli_"


def _dotenv_value(key: str) -> str | None:
    """Read a raw value from the same .env files Pydantic Settings will use.

    Later ``get_settings()`` re-reads these files through Pydantic; this
    helper gives us module-related keys before the full model (and its
    provider-id validation) is instantiated.
    """

    from config.settings import _env_files

    for env_file in _env_files():
        if not env_file.is_file():
            continue
        try:
            values = dotenv_values(env_file)
        except OSError:
            continue
        if key in values:
            value = values[key]
            return "" if value is None else value
    return None


def modules_enabled() -> bool:
    """Return whether module loading is requested before Settings exists."""

    value = _dotenv_value("FCC_MODULES_ENABLED")
    if value is None:
        value = os.environ.get("FCC_MODULES_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in {"", "false", "0", "no", "off"}


def modules_dir() -> Path:
    """Return the modules directory before Settings exists."""

    value = _dotenv_value("FCC_MODULES_DIR") or os.environ.get("FCC_MODULES_DIR")
    if value:
        return Path(os.path.expanduser(value))

    from config.paths import modules_dir_path

    return modules_dir_path()


def is_module_path(path: Path) -> bool:
    """Return True for loadable top-level module files/packages."""

    if path.name.startswith("_"):
        return False
    if not path.exists():
        return False
    return (path.is_file() and path.suffix == ".py") or (
        path.is_dir() and (path / "__init__.py").is_file()
    )


def discover_module_paths(modules_dir: Path) -> list[Path]:
    """Discover candidate top-level module files and packages."""

    if not modules_dir.is_dir():
        return []

    candidates = [entry for entry in modules_dir.iterdir() if is_module_path(entry)]
    candidates.sort(key=lambda p: p.name)
    return candidates


def _path_to_module_name(path: Path, *, prefix: str) -> str:
    """Create a deterministic, unique module name for a file/package path.

    A short hash suffix prevents collisions when different paths share the
    same underscore-escaped stem (e.g. ``a-b.py`` and ``a_b.py``).
    """

    resolved = path.resolve().as_posix()
    escaped = resolved.replace("/", "_").replace(".", "_")
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{escaped}_{digest}"


def load_python_module(path: Path, *, prefix: str = _MODULE_FILE_PREFIX) -> Any:
    """Import a Python file or package from an arbitrary path.

    ``prefix`` is used to namespace the synthetic module name. The CLI uses a
    different prefix so importing a module for command collection does not
    collide with the server's import of the same file.
    """

    module_name = _path_to_module_name(path, prefix=prefix)
    if path.is_file():
        spec = importlib.util.spec_from_file_location(module_name, path)
    else:
        init_file = path / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            module_name, init_file, submodule_search_locations=[str(path)]
        )

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
