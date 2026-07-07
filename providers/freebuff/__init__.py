"""Freebuff2API provider (OpenAI-compatible chat completions via managed proxy)."""

from providers.defaults import FREEBUFF_DEFAULT_BASE

from .binary_manager import binary_status, check_container_running
from .client import FreebuffProvider
from .credentials import credentials_status, read_auth_tokens
from .manager import FreebuffManager

__all__ = [
    "FREEBUFF_DEFAULT_BASE",
    "FreebuffManager",
    "FreebuffProvider",
    "binary_status",
    "check_container_running",
    "credentials_status",
    "read_auth_tokens",
]
