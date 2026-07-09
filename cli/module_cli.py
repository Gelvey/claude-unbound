"""Synchronous loader for module-registered CLI subcommands.

The CLI is a separate process from the FastAPI server, so we can't share
state via ``app.state``. Instead this loader walks the modules directory,
imports each module, and only collects CLI command registrations.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.modules._discovery import (
    discover_module_paths,
    load_python_module,
    modules_dir,
    modules_enabled,
)
from api.modules.contracts import Module, ModuleCliCommand

_CLI_MODULE_PREFIX = "claude_unbound_cli_"


def _extract_module(module: Any) -> Module:
    if hasattr(module, "setup_module"):
        setup = module.setup_module
        if not callable(setup):
            raise TypeError(f"setup_module in {module.__name__} is not callable")
        # The CLI has no FastAPI app or Settings instance; modules that use a
        # setup function for CLI command registration should be side-effect free.
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

    if not modules_enabled():
        logger.debug("Custom modules disabled via FCC_MODULES_ENABLED")
        return []

    modules_path = modules_dir()
    if not modules_path.is_dir():
        logger.debug("Custom modules directory does not exist: {}", modules_path)
        return []

    commands: list[ModuleCliCommand] = []
    for entry in discover_module_paths(modules_path):
        label = entry.stem if entry.is_file() else entry.name
        try:
            raw = load_python_module(entry, prefix=_CLI_MODULE_PREFIX)
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
