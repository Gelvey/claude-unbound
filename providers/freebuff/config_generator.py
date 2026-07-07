"""Generate Freebuff2API config.json from credentials and settings.

The config format is::

    {
      "LISTEN_ADDR": ":<port>",
      "UPSTREAM_BASE_URL": "https://www.codebuff.com",
      "AUTH_TOKENS": ["token1", "token2", ...],
      "ROTATION_INTERVAL": "6h",
      "REQUEST_TIMEOUT": "15m",
      "API_KEYS": [],
      "HTTP_PROXY": ""
    }
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from loguru import logger

# Default upstream for Freebuff2API.
_UPSTREAM_BASE_URL = "https://www.codebuff.com"

# Default rotation interval (how often upstream agent runs are rotated).
_DEFAULT_ROTATION_INTERVAL = "6h"

# Default request timeout.
_DEFAULT_REQUEST_TIMEOUT = "15m"


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def generate_config(
    auth_tokens: list[str],
    *,
    port: int | None = None,
    api_keys: list[str] | None = None,
    http_proxy: str = "",
    rotation_interval: str = _DEFAULT_ROTATION_INTERVAL,
    request_timeout: str = _DEFAULT_REQUEST_TIMEOUT,
    upstream_base_url: str = _UPSTREAM_BASE_URL,
) -> dict[str, Any]:
    """Generate a Freebuff2API config dict.

    Args:
        auth_tokens: List of Freebuff auth tokens (from credentials.json).
        port: Listen port.  If None, a free port is chosen automatically.
        api_keys: Optional API keys for proxy-side auth.  Empty = open access.
        http_proxy: Optional HTTP proxy URL for upstream traffic.
        rotation_interval: How often to rotate upstream agent runs.
        request_timeout: HTTP request timeout for upstream calls.
        upstream_base_url: Upstream codebuff.com URL.

    Returns:
        Config dict ready to be written as JSON.
    """
    if not auth_tokens:
        raise ValueError("At least one auth token is required")

    if port is None:
        port = _find_free_port()

    return {
        "LISTEN_ADDR": f":{port}",
        "UPSTREAM_BASE_URL": upstream_base_url,
        "AUTH_TOKENS": auth_tokens,
        "ROTATION_INTERVAL": rotation_interval,
        "REQUEST_TIMEOUT": request_timeout,
        "API_KEYS": api_keys or [],
        "HTTP_PROXY": http_proxy,
    }


def write_config(
    config: dict[str, Any],
    config_path: Path,
) -> Path:
    """Write the config dict to a JSON file.

    Args:
        config: Config dict from :func:`generate_config`.
        config_path: Path to write the config file.

    Returns:
        The resolved config file path.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "FREEBUFF_CONFIG: wrote config path={} port={}",
        config_path,
        config.get("LISTEN_ADDR"),
    )
    return config_path


def config_path() -> Path:
    """Return the default config file path."""
    from .binary_manager import install_dir

    return install_dir() / "config.json"


def read_config_port() -> int | None:
    """Read the port from the existing config file, or None if not found."""
    path = config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        listen_addr = data.get("LISTEN_ADDR", ":8080")
        # Parse ":8080" → 8080.
        port_str = listen_addr.split(":")[-1]
        return int(port_str)
    except OSError, json.JSONDecodeError, ValueError:
        return None
