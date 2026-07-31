"""Graphify lifecycle manager — facade re-exporting the split submodules.

The original monolithic ``manager.py`` has been split into:

- :mod:`api.graphify.graphify_probes`  — module-level constants + probe helpers.
- :mod:`api.graphify.graphify_helpers`  — venv management + filesystem helpers.
- :mod:`api.graphify.graphify_process`  — ``ProcessMixin`` (server lifecycle).
- :mod:`api.graphify.graphify_coordinator`  — ``CoordinatorMixin`` (indexing).

This module is the facade: it defines ``GraphifyManager`` (inheriting both
mixins) and re-exports every previously-importable name so all existing
imports from ``api.graphify.manager`` keep resolving.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import httpx

from config.settings import Settings, get_settings

from .claude_mcp import (
    graphify_claude_server_registered,
    register_graphify_claude_server,
    unregister_graphify_claude_server,
)
from .config import GraphifyProject
from .graphify_coordinator import CoordinatorMixin
from .graphify_helpers import (
    _directory_size,
    _ensure_graphify_venv,
    _find_free_port,
    _format_bytes,
    _is_graphify_importable,
    _is_module_importable,
    _pip_path,
    _venv_python_path,
)
from .graphify_probes import (
    _FCC_PROVIDER_PREFIXES,
    _GRAPHIFY_BACKEND_ALIAS,
    _GRAPHIFY_LLM_ENV_KEYS,
    _GRAPHIFY_LLM_EXTRAS,
    _GRAPHIFY_OPENAI_EXTRA,
    _GRAPHIFY_OPENAI_SDK_BACKENDS,
    _GRAPHIFY_PACKAGE,
    _GRAPHIFY_PROVIDER_KEY_FALLBACK,
    _MCP_INITIALIZE_BODY,
    _extract_jsonrpc_error,
    _looks_like_timeout_error,
    _parse_sse_data,
    _probe_graphify_port,
    _strip_fcc_model_prefix,
)
from .graphify_process import ProcessMixin
from .projects import load_project_registry

__all__ = [
    "_FCC_PROVIDER_PREFIXES",
    "_GRAPHIFY_BACKEND_ALIAS",
    "_GRAPHIFY_LLM_ENV_KEYS",
    "_GRAPHIFY_LLM_EXTRAS",
    "_GRAPHIFY_OPENAI_EXTRA",
    "_GRAPHIFY_OPENAI_SDK_BACKENDS",
    "_GRAPHIFY_PACKAGE",
    "_GRAPHIFY_PROVIDER_KEY_FALLBACK",
    "_MCP_INITIALIZE_BODY",
    "GraphifyManager",
    "_directory_size",
    "_ensure_graphify_venv",
    "_extract_jsonrpc_error",
    "_find_free_port",
    "_format_bytes",
    "_is_graphify_importable",
    "_is_module_importable",
    "_looks_like_timeout_error",
    "_parse_sse_data",
    "_pip_path",
    "_probe_graphify_port",
    "_strip_fcc_model_prefix",
    "_venv_python_path",
    "get_settings",
    "graphify_claude_server_registered",
    "register_graphify_claude_server",
    "unregister_graphify_claude_server",
]


class GraphifyManager(ProcessMixin, CoordinatorMixin):
    """Manage a local Graphify HTTP MCP server and project registry.

    Lifecycle:
        1. :meth:`setup` -- ensure ``graphifyy`` is importable, installing an
           isolated venv if necessary.
        2. :meth:`start` -- spawn ``python -m graphify.serve``, write the MCP
           backend entry, and restart the MCP router.
        3. :meth:`health_check` -- probe the Graphify ``/mcp`` endpoint.
        4. :meth:`stop` -- terminate the server, remove the MCP backend, and
           restart the router.
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._port: int | None = None
        self._base_url: str | None = None
        self._python_path: str | None = None
        self._last_error: str | None = None
        self._watcher: Any | None = None
        # True only when *this* manager spawned the running graphify process.
        # An adopted server (already running on the target port, owned by a
        # concurrent or prior fcc-server instance) is not ours to kill, and a
        # later stop() must NOT remove the ~/.claude.json entry for it — that is
        # what lets a short-lived sibling fcc-server instance shut down without
        # tearing down graphify a long-lived instance depends on.
        self._owns_process: bool = False
        self._adopted: bool = False

        # --- Single-index queue (one project indexes at a time) ---
        self._index_queue: deque[
            tuple[GraphifyProject, asyncio.Future[dict[str, Any]]]
        ] = deque()
        self._index_queue_paths: set[str] = set()
        self._index_current: str | None = None
        self._index_current_future: asyncio.Future[dict[str, Any]] | None = None
        self._index_event = asyncio.Event()
        self._index_worker_task: asyncio.Task[None] | None = None

    @property
    def _settings(self) -> Settings:
        """Always return the current settings.

        The admin UI writes new values to the managed ``.env`` file and
        clears the :func:`get_settings` LRU cache.  By reading from the
        cache on every access the manager picks up changed LLM backend,
        model, and API-key values without requiring an fcc-server restart.
        """
        return get_settings()

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def base_url(self) -> str | None:
        return self._base_url

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def is_running(self) -> bool:
        if self._process is not None and self._process.returncode is None:
            return True
        return self._adopted

    async def health_check(self) -> dict[str, Any]:
        """Probe the Graphify ``/mcp`` endpoint with an MCP initialize request.

        Graphify's Streamable HTTP server rejects a plain ``GET /mcp`` with
        ``406 Not Acceptable``; a POSTed ``initialize`` carrying the SSE
        ``Accept`` header is the correct liveness probe and returns 200 with an
        SSE-framed ``serverInfo`` payload.
        """
        if not self._base_url:
            return {"status": "not_configured", "error": "Graphify is not running"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await self._probe_mcp(client)
        except httpx.HTTPError as exc:
            return {"status": "unreachable", "error": str(exc)}
        data = _parse_sse_data(resp.text)
        if resp.status_code == 200:
            server_info = None
            if isinstance(data, dict):
                result = data.get("result")
                if isinstance(result, dict):
                    server_info = result.get("serverInfo")
            return {
                "status": "healthy",
                "http_status": resp.status_code,
                "server_info": server_info,
                "data": data,
            }
        return {
            "status": "unhealthy",
            "http_status": resp.status_code,
            "data": data,
            "error": _extract_jsonrpc_error(data) or f"HTTP {resp.status_code}",
        }

    def status(self) -> dict[str, Any]:
        """Return fast in-memory status for the admin panel."""
        registry = load_project_registry()
        return {
            "enabled": self._settings.graphify_enabled,
            "running": self.is_running,
            "port": self._port,
            "base_url": self._base_url,
            "python": self._python_path or self._resolve_python(),
            "last_error": self._last_error,
            "mcp_registered": graphify_claude_server_registered(),
            "owns_process": self._owns_process,
            "adopted": self._adopted,
            "llm_backend": self._settings.graphify_llm_backend,
            "llm_model": self._settings.graphify_llm_model,
            "code_only": self._settings.graphify_code_only,
            "projects_count": len(registry.projects),
            "projects_summary": [
                {
                    "path": p.path,
                    "name": p.name,
                    "status": p.status,
                    "last_indexed": p.last_indexed.isoformat()
                    if p.last_indexed
                    else None,
                }
                for p in registry.projects
            ],
            "index_queue": self.index_queue_snapshot,
            "index_queue_length": len(self._index_queue)
            + (1 if self._index_current else 0),
        }
