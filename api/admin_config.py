"""Admin UI configuration manifest and managed env persistence.

Facade module that re-exports the public surface split across:
- :mod:`api.admin_manifest` — field specs, sections, and lookup indexes.
- :mod:`api.admin_env` — read/write/validate ``.env`` persistence.
- :mod:`api.admin_status` — provider status and Claude permissions helpers.

All names previously importable from ``api.admin_config`` remain available here.
"""

from __future__ import annotations

from api.admin_env import (
    _display_value,
    _dotenv_values_from_file,
    _dotenv_values_from_text,
    _effective_values_for_validation,
    _field_input_key,
    _format_validation_errors,
    _is_locked_source,
    _load_value_state,
    _normalize_for_env,
    _quote_env_value,
    _target_values_with_updates,
    _template_text,
    changed_pending_fields,
    configured_env_files,
    explicit_env_path,
    load_config_response,
    render_env_file,
    repo_env_path,
    template_values,
    validate_updates,
    validate_values,
    write_managed_env,
)
from api.admin_manifest import (
    CLAUDE_SETTINGS_PATH,
    FIELD_BY_KEY,
    FIELDS,
    MASKED_SECRET,
    SECTIONS,
    ConfigFieldSpec,
    ConfigSectionSpec,
    FieldType,
    SourceType,
    env_keys,
    fields_with_attrs,
)
from api.admin_status import (
    _MULTI_CREDENTIAL_ENVS,
    _value_for_settings_attr,
    provider_config_status,
    read_claude_permissions_setting,
    write_claude_permissions_setting,
)

__all__ = [
    "CLAUDE_SETTINGS_PATH",
    "FIELDS",
    "FIELD_BY_KEY",
    "MASKED_SECRET",
    "SECTIONS",
    "_MULTI_CREDENTIAL_ENVS",
    "ConfigFieldSpec",
    "ConfigSectionSpec",
    "FieldType",
    "SourceType",
    "_display_value",
    "_dotenv_values_from_file",
    "_dotenv_values_from_text",
    "_effective_values_for_validation",
    "_field_input_key",
    "_format_validation_errors",
    "_is_locked_source",
    "_load_value_state",
    "_normalize_for_env",
    "_quote_env_value",
    "_target_values_with_updates",
    "_template_text",
    "_value_for_settings_attr",
    "changed_pending_fields",
    "configured_env_files",
    "env_keys",
    "explicit_env_path",
    "fields_with_attrs",
    "load_config_response",
    "provider_config_status",
    "read_claude_permissions_setting",
    "render_env_file",
    "repo_env_path",
    "template_values",
    "validate_updates",
    "validate_values",
    "write_claude_permissions_setting",
    "write_managed_env",
]
