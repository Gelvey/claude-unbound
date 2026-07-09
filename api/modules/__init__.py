"""Public API for Claude Unbound custom modules."""

from __future__ import annotations

from .contracts import Module
from .errors import ModuleError, ModuleLoadError, ModuleRegistrationError
from .loader import ModuleManager


def module(name: str, *, version: str = "0.0.0") -> Module:
    """Start building a new module with a fluent API."""

    return Module(name=name, version=version)


__all__ = [
    "Module",
    "ModuleError",
    "ModuleLoadError",
    "ModuleManager",
    "ModuleRegistrationError",
    "module",
]
