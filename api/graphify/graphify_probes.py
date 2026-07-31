"""Module-level constants and probe helpers for the Graphify manager.

Extracted from ``manager.py`` to keep the facade thin. These are pure
functions and module-level constants with no class-state dependency.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_GRAPHIFY_PACKAGE = "graphifyy[mcp]"

# Map a configured LLM backend to the env var graphify's extractor reads for its
# API key (see graphify/llm.py). Used so the semantic extraction pass can run
# without leaking the key into fcc-server's own environment.
_GRAPHIFY_LLM_ENV_KEYS: dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "lmstudio": "OPENAI_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
}

# graphify has no native "cloudflare" backend. We ride its OpenAI-compatible ``openai``
# backend (vision-capable, ``_call_openai_compat``) and redirect it at Cloudflare's
# OpenAI-compatible Workers AI endpoint via ``OPENAI_BASE_URL``. See graphify/llm.py
# ``BACKENDS["openai"]``. Maps a configured backend to the graphify ``--backend`` value
# we pass on the CLI.
_GRAPHIFY_BACKEND_ALIAS: dict[str, str] = {
    "cloudflare": "openai",
    "lmstudio": "openai",
    "anthropic": "claude",
}

# Backends whose extractor routes through graphify's ``_call_openai_compat`` and so
# requires the ``openai`` python package in the graphify venv. Cloudflare is included
# because it rides the ``openai`` backend. ``claude``/``anthropic`` need ``anthropic``.
_GRAPHIFY_OPENAI_SDK_BACKENDS: frozenset[str] = frozenset(
    {"cloudflare", "openai", "gemini", "deepseek", "kimi", "ollama", "lmstudio"}
)

# When GRAPHIFY_LLM_API_KEY is empty, fall back to the matching Claude Unbound provider
# key already configured on the Providers tab, so the user does not re-enter it.
_GRAPHIFY_PROVIDER_KEY_FALLBACK: dict[str, str] = {
    "cloudflare": "cloudflare_ai_api_key",
    "gemini": "gemini_api_key",
    "deepseek": "deepseek_api_key",
    "kimi": "kimi_api_key",
}

# graphifyy extra that installs the python SDK a backend's extractor imports.
_GRAPHIFY_LLM_EXTRAS: dict[str, str] = {
    "claude": "anthropic",
    "anthropic": "anthropic",
}
_GRAPHIFY_OPENAI_EXTRA = "openai"


_FCC_PROVIDER_PREFIXES: frozenset[str] = frozenset(
    {
        "cloudflare_ai",
        "lmstudio",
        "llamacpp",
        "ollama",
        "open_router",
        "nvidia_nim",
        "gemini",
        "deepseek",
        "mistral",
        "mistral_codestral",
        "kimi",
        "groq",
        "cerebras",
        "fireworks",
        "opencode",
        "opencode_go",
        "wafer",
        "zai",
    }
)


def _looks_like_timeout_error(text: str) -> bool:
    """Return True if *text* looks like a provider request timeout."""
    lowered = text.lower()
    return any(
        marker in lowered for marker in ("request timed out", "timed out", "timeout")
    )


def _strip_fcc_model_prefix(model: str) -> str:
    """Strip the FCC provider prefix from a model id.

    FCC's Model Config stores models as ``provider/model_id`` (e.g.
    ``cloudflare_ai/@cf/moonshotai/kimi-k2.7-code``).  Graphify expects the
    bare provider-native id (``@cf/moonshotai/kimi-k2.7-code``).  The prefix
    is always the first ``/``-delimited segment when it matches a known FCC
    provider id — model ids themselves can contain ``/`` (e.g.
    ``@cf/meta/llama-3.3-70b-instruct-fp8-fast``), so we only strip when the
    first segment is a recognised provider prefix.
    """
    if "/" in model:
        prefix = model.split("/", 1)[0]
        if prefix in _FCC_PROVIDER_PREFIXES:
            return model[len(prefix) + 1 :]
    return model


# MCP ``initialize`` request body used by the readiness/health probes. Graphify
# serves a Streamable HTTP endpoint at /mcp that rejects plain GET with 406
# ("Client must accept text/event-stream"); a POSTed initialize with the SSE
# Accept header is the canonical liveness check and returns 200.
_MCP_INITIALIZE_BODY: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "fcc-graphify", "version": "0"},
    },
}


def _parse_sse_data(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a Streamable HTTP SSE response body.

    The graphify server answers the initialize probe with an
    ``event: message\\ndata: {...}`` body rather than bare JSON, so a plain
    ``response.json()`` parse fails. This pulls the ``data:`` payload.
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if not payload:
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return None


def _extract_jsonrpc_error(data: dict[str, Any] | None) -> str | None:
    """Return a human-readable error message from a JSON-RPC error payload."""
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return None


async def _probe_graphify_port(port: int, api_key: str = "") -> bool:
    """Return True if a healthy Graphify MCP server answers on ``port``.

    Used by :meth:`GraphifyManager.start` to detect a server already running on
    the target port (a survivor of a forcefully-killed prior fcc-server, or one
    owned by a concurrent instance) so the manager can adopt it instead of
    spawning a duplicate. Mirrors the readiness/health probe: a POSTed MCP
    ``initialize`` carrying the SSE ``Accept`` header, returning 200 on health.
    """
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"http://127.0.0.1:{port}/mcp",
                json=_MCP_INITIALIZE_BODY,
                headers=headers,
            )
    except httpx.HTTPError:
        return False
    return resp.status_code == 200
