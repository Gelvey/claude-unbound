"""Dynamic Settings model built from module-declared fields.

Each module that wants its own typed config declares fields via
``Module.setting(alias=..., type=..., default=...)``. After the module
loader collects every declaration, this module builds a single Pydantic
``BaseSettings`` subclass and exposes it through :func:`get_module_settings`.
The model reads the same dotenv files as the main :class:`config.settings.Settings`
so a module's ``MY_PLUGIN_API_KEY`` can be configured in ``.env`` like any
other setting.

The model is rebuilt on every :func:`get_module_settings` call. The
underlying field list is mutated by :func:`rebuild_module_settings` (per
``ModuleManager.load_for_app``) and cleared by :func:`clear_module_settings`
(for tests). Pydantic instantiation is fast for a small model, so no
extra cache is used.
"""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings import _env_files

_MODULE_FIELDS: list[Any] = []


def _module_env_files() -> tuple[str, ...]:
    """Dotenv files the dynamic ModuleSettings reads from, as plain strings."""

    return tuple(str(p) for p in _env_files())


def _build_model() -> type[BaseSettings]:
    """Build a fresh ``ModuleSettings`` model from the current field list."""

    if not _MODULE_FIELDS:
        return BaseSettings

    namespace: dict[str, Any] = {
        "model_config": SettingsConfigDict(
            env_file=_module_env_files(),
            extra="ignore",
            case_sensitive=False,
        ),
    }
    annotations: dict[str, Any] = {}
    for spec in _MODULE_FIELDS:
        field_name = spec.alias.lower()
        if field_name in annotations:
            # Last write wins; the loader de-duplicates within a single load.
            continue
        namespace[field_name] = spec.default
        annotations[field_name] = spec.type
    namespace["__annotations__"] = annotations

    return type("ModuleSettings", (BaseSettings,), namespace)


def rebuild_module_settings(specs: list[Any]) -> None:
    """Replace the registered field list.

    ``specs`` is a list of :class:`api.modules.contracts.ModuleSettingSpec`.
    Last-write-wins on duplicate aliases.
    """

    global _MODULE_FIELDS
    _MODULE_FIELDS = list(specs)


def clear_module_settings() -> None:
    """Drop the field list (used by tests)."""

    global _MODULE_FIELDS
    _MODULE_FIELDS = []


def get_module_settings() -> BaseSettings:
    """Return the current ``ModuleSettings`` instance.

    The instance is rebuilt on every call from the current field list. If
    no module has declared a setting yet, an empty ``BaseSettings`` is
    returned.
    """

    return _build_model()()


__all__ = [
    "clear_module_settings",
    "get_module_settings",
    "rebuild_module_settings",
]
