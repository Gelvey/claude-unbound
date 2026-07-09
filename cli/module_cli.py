"""Synchronous loader for module-registered CLI subcommands.

The CLI is a separate process from the FastAPI server, so we can't share
state via ``app.state``. Instead this loader walks the modules directory,
imports each module, and only collects CLI command registrations.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from loguru import logger

from api.modules.contracts import Module, ModuleCliCommand
from config.paths import modules_dir_path


def _dotenv_value(key: str) -> str | None:
    from config.settings import _env_files

    for env_file in _env_files():
        if not env_file.is_file():
            continue
        try:
            from dotenv import dotenv_values

            values = dotenv_values(env_file)
        except OSError:
            continue
        if key in values:
            value = values[key]
            return "" if value is None else value
    return None


def _modules_enabled() -> bool:
    value = _dotenv_value("FCC_MODULES_ENABLED")
    if value is None:
        value = os.environ.get("FCC_MODULES_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in {"", "false", "0", "no", "off"}


def _modules_dir() -> Path:
    value = _dotenv_value("FCC_MODULES_DIR") or os.environ.get("FCC_MODULES_DIR")
    if value:
        return Path(os.path.expanduser(value))
    return modules_dir_path()


def _is_module_path(path: Path) -> bool:
    if path.name.startswith("_"):
        return False
    if not path.exists():
        return False
    return (path.is_file() and path.suffix == ".py") or (
        path.is_dir() and (path / "__init__.py").is_file()
    )


def _load_python_module(path: Path) -> Any:
    module_name = f"claude_unbound_cli_{path.resolve().as_posix().replace('/', '_').replace('.', '_')}"
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


def _extract_module(module: Any) -> Module:
    if hasattr(module, "setup_module"):
        setup = module.setup_module
        if not callable(setup):
            raise TypeError(f"setup_module in {module.__name__} is not callable")
        result = setup(None, None)
        if result is None:
            raise TypeError(f"setup_module in {module.__name__} returned None")
        return result
    if hasattr(module, "FCC_MODULE"):
        return module.FCC_MODULE
    raise AttributeError(
        f"Module {module.__name__} has no FCC_MODULE or setup_module attribute"
    )


def collect_cli_commands() -> list[ModuleCliCommand]:
    """Discover, import, and collect every module-registered CLI command.

    Failed modules are logged and skipped. The returned list is empty when
    modules are disabled or the modules directory does not exist.
    """

    if not _modules_enabled():
        logger.debug("Custom modules disabled via FCC_MODULES_ENABLED")
        return []

    modules_dir = _modules_dir()
    if not modules_dir.is_dir():
        logger.debug("Custom modules directory does not exist: {}", modules_dir)
        return []

    commands: list[ModuleCliCommand] = []
    for entry in sorted(modules_dir.iterdir(), key=lambda p: p.name):
        if not _is_module_path(entry):
            continue
        label = entry.stem if entry.is_file() else entry.name
        try:
            raw = _load_python_module(entry)
        except Exception as exc:
            logger.error(
                "Failed to import module '{}': exc_type={}", label, type(exc).__name__
            )
            continue
        try:
            module = _extract_module(raw)
        except Exception as exc:
            logger.error(
                "Failed to configure module '{}': exc_type={}",
                label,
                type(exc).__name__,
            )
            continue
        if not isinstance(module, Module):
            logger.error(
                "Module '{}' FCC_MODULE/setup_module returned type {}, expected Module",
                label,
                type(module).__name__,
            )
            continue
        commands.extend(module.cli_commands)

    return commands


__all__ = ["collect_cli_commands"]
