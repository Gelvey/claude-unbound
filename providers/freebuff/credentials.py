"""Read Freebuff auth tokens from ~/.config/manicode/credentials.json.

The Freebuff CLI (``npm i -g freebuff && freebuff``) saves auth tokens to
``~/.config/manicode/credentials.json``.  The file format is::

    {
      "default": {
        "authToken": "fa82b5c1-e39d-...",
        ...
      },
      "profile2": {
        "authToken": "abc123...",
        ...
      }
    }

Each top-level key is a profile name.  We extract all non-empty ``authToken``
values and return them as a list for use as ``AUTH_TOKENS`` in the Freebuff2API
config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

# Default path where the Freebuff CLI stores credentials.
_DEFAULT_CREDENTIALS_PATH = Path.home() / ".config" / "manicode" / "credentials.json"


def credentials_path(override: str | Path | None = None) -> Path:
    """Return the resolved credentials file path."""
    if override is not None:
        return Path(override).expanduser()
    return _DEFAULT_CREDENTIALS_PATH


def read_auth_tokens(path: str | Path | None = None) -> list[str]:
    """Read all auth tokens from the Freebuff credentials file.

    Returns:
        List of non-empty auth token strings.  Returns an empty list if the
        file does not exist, is malformed, or contains no tokens.
    """
    resolved = credentials_path(path)
    if not resolved.is_file():
        logger.debug("FREEBUFF_CREDENTIALS: file not found path={}", resolved)
        return []

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "FREEBUFF_CREDENTIALS: failed to read path={} error={}",
            resolved,
            exc,
        )
        return []

    if not isinstance(data, dict):
        logger.warning(
            "FREEBUFF_CREDENTIALS: unexpected format path={} type={}",
            resolved,
            type(data).__name__,
        )
        return []

    tokens: list[str] = []
    for profile_name, profile_data in data.items():
        if not isinstance(profile_data, dict):
            continue
        token = profile_data.get("authToken", "")
        if isinstance(token, str) and token.strip():
            tokens.append(token.strip())
            logger.debug("FREEBUFF_CREDENTIALS: found token profile={}", profile_name)

    logger.info("FREEBUFF_CREDENTIALS: loaded tokens={} path={}", len(tokens), resolved)
    return tokens


def credentials_status(path: str | Path | None = None) -> dict[str, Any]:
    """Return credential status for the admin panel.

    Returns:
        Dict with ``found`` (bool), ``path`` (str), ``profiles`` (list of
        profile names with tokens), and ``token_count`` (int).
    """
    resolved = credentials_path(path)
    if not resolved.is_file():
        return {
            "found": False,
            "path": str(resolved),
            "profiles": [],
            "token_count": 0,
        }

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {
            "found": False,
            "path": str(resolved),
            "profiles": [],
            "token_count": 0,
        }

    if not isinstance(data, dict):
        return {
            "found": False,
            "path": str(resolved),
            "profiles": [],
            "token_count": 0,
        }

    profiles: list[str] = []
    for profile_name, profile_data in data.items():
        if not isinstance(profile_data, dict):
            continue
        token = profile_data.get("authToken", "")
        if isinstance(token, str) and token.strip():
            profiles.append(profile_name)

    return {
        "found": True,
        "path": str(resolved),
        "profiles": profiles,
        "token_count": len(profiles),
    }
