"""Gateway-safe model id encoding for Claude Code model discovery."""

from __future__ import annotations

from dataclasses import dataclass

GATEWAY_MODEL_ID_PREFIX = "anthropic"

# Claude Code currently treats any model id containing ``claude-3-`` as not
# supporting thinking. This intentionally uses that client-side capability
# heuristic while keeping the real provider/model ref reversible for routing.
NO_THINKING_GATEWAY_MODEL_ID_PREFIX = "claude-3-freecc-no-thinking"

# Claude Code reports a 1M-token context window for any model id matching
# ``/\[1m\]/i`` and strips the marker before its own capability lookups. The
# gateway appends this suffix to advertise 1M-context models and removes it
# again before routing, so it never reaches the upstream provider.
CONTEXT_WINDOW_1M_MARKER = "[1m]"


@dataclass(frozen=True, slots=True)
class DecodedGatewayModelId:
    provider_id: str
    provider_model: str
    force_thinking_enabled: bool | None = None


def strip_context_window_marker(model_ref: str) -> str:
    """Remove a trailing ``[1m]`` context-window marker, if present."""
    if model_ref.lower().endswith(CONTEXT_WINDOW_1M_MARKER):
        return model_ref[: -len(CONTEXT_WINDOW_1M_MARKER)]
    return model_ref


def gateway_model_id(
    provider_model_ref: str, *, context_window_1m: bool = False
) -> str:
    """Return the normal Claude Code-discoverable id for a provider/model ref."""
    model_id = f"{GATEWAY_MODEL_ID_PREFIX}/{provider_model_ref}"
    return f"{model_id}{CONTEXT_WINDOW_1M_MARKER}" if context_window_1m else model_id


def no_thinking_gateway_model_id(
    provider_model_ref: str, *, context_window_1m: bool = False
) -> str:
    """Return a Claude Code-discoverable id that disables client thinking."""
    model_id = f"{NO_THINKING_GATEWAY_MODEL_ID_PREFIX}/{provider_model_ref}"
    return f"{model_id}{CONTEXT_WINDOW_1M_MARKER}" if context_window_1m else model_id


def decode_gateway_model_id(model_name: str) -> DecodedGatewayModelId | None:
    """Decode a model id advertised by this gateway, if it is one."""
    prefix, separator, remainder = model_name.partition("/")
    if not separator:
        return None

    force_thinking_enabled: bool | None
    if prefix == GATEWAY_MODEL_ID_PREFIX:
        force_thinking_enabled = None
    elif prefix == NO_THINKING_GATEWAY_MODEL_ID_PREFIX:
        force_thinking_enabled = False
    else:
        return None

    provider_id, provider_separator, provider_model = remainder.partition("/")
    if not provider_separator or not provider_model:
        return None

    return DecodedGatewayModelId(
        provider_id=provider_id,
        provider_model=strip_context_window_marker(provider_model),
        force_thinking_enabled=force_thinking_enabled,
    )
