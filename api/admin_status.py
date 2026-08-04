"""Admin status and validation helpers: provider status and Claude permissions."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from api.admin_env import _load_value_state
from api.admin_manifest import FIELDS
from config.provider_catalog import PROVIDER_CATALOG

# Extra required env vars beyond the primary credential for providers that
# need additional settings.  Checked by :func:`provider_config_status`.
# For API-key providers this is beyond ``credential_env``; for ADC providers
# (``static_credential``) it is the project id the static credential alone
# does not carry.
_MULTI_CREDENTIAL_ENVS: dict[str, tuple[str, ...]] = {
    "cloudflare_ai": ("CLOUDFLARE_AI_ACCOUNT_ID",),
    "vertex_ai": ("VERTEX_AI_PROJECT_ID",),
}


def provider_config_status(
    state: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return provider configuration status without making network calls."""

    state = state or _load_value_state()
    statuses: list[dict[str, Any]] = []
    for provider_id, descriptor in PROVIDER_CATALOG.items():
        if "local" in descriptor.capabilities:
            base_url = ""
            if descriptor.base_url_attr is not None:
                base_url = _value_for_settings_attr(state, descriptor.base_url_attr)
            statuses.append(
                {
                    "provider_id": provider_id,
                    "kind": "local",
                    "status": "missing_url" if not base_url.strip() else "unknown",
                    "label": "Missing URL" if not base_url.strip() else "Not checked",
                    "base_url": base_url or descriptor.default_base_url or "",
                }
            )
            continue

        # Remote: API key (credential_env) or ADC (static_credential).
        if descriptor.credential_env is not None:
            value = str(state.get(descriptor.credential_env, {}).get("value", ""))
            primary_ok = bool(value.strip())
        else:
            # static_credential is always present (e.g. Vertex AI ADC).
            primary_ok = True

        missing_extras: list[str] = []
        for extra_env in _MULTI_CREDENTIAL_ENVS.get(provider_id, ()):
            extra_val = str(state.get(extra_env, {}).get("value", ""))
            if not extra_val.strip():
                missing_extras.append(extra_env)

        if not primary_ok:
            status, label = "missing_key", "Missing key"
        elif missing_extras:
            status = "partial"
            label = f"Missing: {', '.join(missing_extras)}"
        else:
            status, label = "configured", "Configured"

        entry: dict[str, Any] = {
            "provider_id": provider_id,
            "kind": "remote",
            "status": status,
            "label": label,
            "credential_env": descriptor.credential_env,
        }
        if missing_extras:
            entry["missing_envs"] = missing_extras
        statuses.append(entry)
    return statuses


def _value_for_settings_attr(
    state: Mapping[str, Mapping[str, Any]], settings_attr: str
) -> str:
    for field in FIELDS:
        if field.settings_attr == settings_attr:
            return str(state.get(field.key, {}).get("value", field.default))
    return ""


def read_claude_permissions_setting() -> bool:
    """Return whether Claude Code is configured to bypass permissions.

    Reads ``~/.claude/settings.json`` and returns ``True`` when
    ``permissions.defaultMode`` is ``"bypassPermissions"``.
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        data = (
            json.loads(settings_path.read_text("utf-8"))
            if settings_path.is_file()
            else {}
        )
    except json.JSONDecodeError, OSError:
        return False
    permissions = data.get("permissions")
    return (
        isinstance(permissions, dict)
        and permissions.get("defaultMode") == "bypassPermissions"
    )


def write_claude_permissions_setting(enabled: bool) -> None:
    """Write ``bypassPermissions`` into ``~/.claude/settings.json``.

    When *enabled* is ``True`` the ``permissions.defaultMode`` key is set to
    ``"bypassPermissions"`` so that all Claude Code sessions skip permission
    prompts.  When *enabled* is ``False`` the key is removed (falling back to
    Claude Code's default interactive mode).

    The file is written atomically via a temporary rename to avoid partial
    writes.
    """

    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                f"Cannot parse existing settings file: {settings_path}"
            ) from exc
    else:
        settings = {}

    permissions = settings.setdefault("permissions", {})
    if enabled:
        permissions["defaultMode"] = "bypassPermissions"
    else:
        permissions.pop("defaultMode", None)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, settings_path)
