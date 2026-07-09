"""Errors raised by the custom module loader."""

from __future__ import annotations


class ModuleError(Exception):
    """Base exception for module system errors."""


class ModuleLoadError(ModuleError):
    """Raised when a module cannot be discovered or imported."""


class ModuleRegistrationError(ModuleError):
    """Raised when a module's registration into a runtime surface fails."""

    def __init__(self, message: str, *, module_name: str, surface: str) -> None:
        super().__init__(message)
        self.module_name = module_name
        self.surface = surface
