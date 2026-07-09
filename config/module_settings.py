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

from typing import Any, get_args

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings import _env_files

_MODULE_FIELDS: list[Any] = []

# Names that would collide with BaseSettings machinery when used as model attrs.
_RESERVED_FIELD_NAMES = frozenset(
    {"model_config", "__annotations__", "__module__", "__qualname__", "__doc__"}
)


def _module_env_files() -> tuple[str, ...]:
    """Dotenv files the dynamic ModuleSettings reads from, as plain strings."""

    return tuple(str(p) for p in _env_files())


def _type_accepts_none(tp: Any) -> bool:
    """Return True when ``tp`` already includes ``None`` as a valid value."""

    if tp is type(None):
        return True
    type_args = get_args(tp)
    return type(None) in type_args


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
        if field_name in _RESERVED_FIELD_NAMES:
            logger.warning(
                "Module setting alias '{}' resolves to reserved name '{}'; skipping",
                spec.alias,
                field_name,
            )
            continue

        field_type = spec.type
        default_value = spec.default
        # A default of None with a non-Optional type would crash model validation
        # whenever the env var is unset. Treat the field as Optional instead.
        if default_value is None and not _type_accepts_none(field_type):
            field_type = field_type | None

        # Last write wins on duplicate aliases (matches rebuild_module_settings docstring).
        namespace[field_name] = default_value
        annotations[field_name] = field_type
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
