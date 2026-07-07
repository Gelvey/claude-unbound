"""Append a constant system-prompt directive without breaking prefix caches.

Provider prefix caches (and Anthropic ``cache_control`` breakpoints) require
exact prefix matches, so the directive is only ever *appended* after existing
system content — never prepended, never merged into existing blocks (which may
carry ``cache_control``). A constant suffix is identical every turn of a
conversation, so cached prefixes keep hitting.
"""

from __future__ import annotations

from typing import Any

from .content import get_block_attr


def _system_contains(system: Any, directive: str) -> bool:
    if isinstance(system, str):
        return directive in system
    if isinstance(system, list):
        for block in system:
            text = get_block_attr(block, "text", "")
            if text and directive in str(text):
                return True
    return False


def _directive_block(system: list, directive: str) -> Any:
    """Build a plain text block matching the shape of the existing blocks."""
    block = {"type": "text", "text": directive}
    if system:
        validate = getattr(type(system[-1]), "model_validate", None)
        if callable(validate):
            return validate(block)
    return block


def append_system_directive(request: Any, directive: str) -> None:
    """Idempotently append ``directive`` to ``request.system`` (in place)."""
    directive = directive.strip()
    if not directive:
        return
    system = getattr(request, "system", None)
    if system is None:
        request.system = directive
    elif _system_contains(system, directive):
        return
    elif isinstance(system, str):
        request.system = f"{system}\n\n{directive}"
    elif isinstance(system, list):
        request.system = [*system, _directive_block(system, directive)]
