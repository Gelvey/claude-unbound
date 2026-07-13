"""Graphify lifecycle manager."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from config.settings import Settings

from .claude_mcp import (
    graphify_claude_server_registered,
    register_graphify_claude_server,
    unregister_graphify_claude_server,
)
from .config import GraphifyProject
from .paths import graphify_venv_dir
from .projects import (
    load_project_registry,
    save_project_registry,
    update_project_status,
)

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


class GraphifyManager:
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

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._process: asyncio.subprocess.Process | None = None
        self._port: int | None = None
        self._base_url: str | None = None
        self._python_path: str | None = None
        self._last_error: str | None = None
        self._indexing_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._watcher: Any | None = None

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
        return self._process is not None and self._process.returncode is None

    def _resolve_python(self) -> str:
        """Return the Python interpreter that should run graphify commands."""
        if self._python_path:
            return self._python_path
        configured = self._settings.graphify_python_path.strip()
        if configured:
            return configured
        if _is_graphify_importable(sys.executable):
            return sys.executable
        venv_python = _venv_python_path(graphify_venv_dir())
        if _is_graphify_importable(venv_python):
            return venv_python
        return sys.executable

    async def setup(self, *, create_venv: bool = True) -> dict[str, Any]:
        """Ensure graphifyy is available, installing to an isolated venv if needed."""
        python = self._resolve_python()
        if _is_graphify_importable(python):
            self._python_path = python
            return {
                "ready": True,
                "python": python,
                "method": "existing" if python == sys.executable else "venv",
            }

        if create_venv and python == sys.executable:
            venv_python = await _ensure_graphify_venv(graphify_venv_dir())
            if _is_graphify_importable(venv_python):
                self._python_path = venv_python
                return {
                    "ready": True,
                    "python": venv_python,
                    "method": "venv",
                }
            python = venv_python

        self._last_error = (
            "graphifyy is not installed. Run setup or install with: "
            f"uv sync --extra graphify  (tried {python})"
        )
        return {"ready": False, "python": python, "error": self._last_error}

    async def start(self) -> bool:
        """Start the Graphify HTTP MCP server."""
        if self.is_running:
            return True

        setup_result = await self.setup(create_venv=True)
        if not setup_result["ready"]:
            self._last_error = setup_result.get("error", "Graphify not available")
            return False

        python = setup_result["python"]
        port = self._settings.graphify_server_port or _find_free_port()
        self._port = port
        self._base_url = f"http://127.0.0.1:{port}"

        # Spawn first, then wait for readiness *before* registering the MCP
        # backend. This keeps the router from ever advertising a port that is
        # not yet listening (and avoids a reload pointing clients at a dead
        # port during the readiness window).
        env = os.environ.copy()
        env["GRAPHIFY_API_KEY"] = self._settings.graphify_api_key or ""
        # Stateless mode makes every MCP request independent so the server
        # does not require an mcp-session-id header. Without it, the upstream
        # graphifyy session manager returns HTTP 400 'Missing session ID'
        # for any tools/call that lacks the (rotating, per-response) session
        # id the Python SDK hands out — Claude Code's TS MCP SDK maps that
        # to the generic "Unable to connect. Is the computer able to access
        # the url?" surfaced as tool failures.
        serve_argv: list[str] = [
            "graphify.serve",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        if self._settings.graphify_stateless:
            serve_argv.append("--stateless")
        try:
            self._process = await asyncio.create_subprocess_exec(
                python,
                "-m",
                *serve_argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
        except Exception as exc:
            self._last_error = str(exc)
            return False

        if not await self._wait_for_ready():
            self._last_error = "Graphify health check timed out"
            await self.stop()
            return False

        # Server is confirmed up: register it as a sibling Claude Code MCP
        # server (in ~/.claude.json mcpServers, alongside mcp-router). Graphify
        # is not a backend inside the MCP Router — Claude Code connects to it
        # directly over loopback HTTP.
        register_graphify_claude_server(port, self._settings.graphify_api_key)

        self._last_error = None
        logger.info(
            "GRAPHIFY_MANAGER: started port={} python={}",
            port,
            python,
        )
        self._start_watcher()
        if self._settings.graphify_auto_index_on_start:
            await self._auto_index_projects()
        return True

    async def stop(self) -> None:
        """Stop Graphify and remove its MCP backend."""
        await self._stop_watcher()
        process = self._process
        self._process = None
        if process and process.returncode is None:
            try:
                process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                with contextlib.suppress(ProcessLookupError):
                    await process.wait()
            except ProcessLookupError:
                pass
        self._port = None
        self._base_url = None
        await self._remove_backend_silently()
        logger.info("GRAPHIFY_MANAGER: stopped")

    async def restart(self) -> bool:
        """Restart the Graphify server."""
        await self.stop()
        return await self.start()

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
        }

    async def index_project(self, project: GraphifyProject) -> dict[str, Any]:
        """Run ``graphify extract`` (or ``update`` if graph exists) for *project*."""
        setup_result = await self.setup(create_venv=True)
        if not setup_result["ready"]:
            return {
                "success": False,
                "error": setup_result.get("error", "Graphify not available"),
            }

        python = setup_result["python"]
        repo_path = Path(project.path)

        # Ensure the graphify venv has the LLM SDK the configured backend imports.
        # The venv is created with only graphifyy[mcp] (no openai/anthropic), so
        # without this every cloud backend raises ImportError mid-extract.
        try:
            await self._ensure_graphify_llm_extra(python)
        except Exception as exc:
            error = str(exc)
            registry = load_project_registry()
            update_project_status(
                registry, project.path, status="error", error_message=error
            )
            save_project_registry(registry)
            return {"success": False, "error": error}

        max_bytes = getattr(self._settings, "graphify_max_project_bytes", 0)
        if max_bytes > 0:
            size = _directory_size(repo_path)
            if size > max_bytes:
                error = (
                    f"Project size ({_format_bytes(size)}) exceeds "
                    f"GRAPHIFY_MAX_PROJECT_BYTES ({_format_bytes(max_bytes)})"
                )
                registry = load_project_registry()
                update_project_status(
                    registry, project.path, status="error", error_message=error
                )
                save_project_registry(registry)
                return {"success": False, "error": error}

        graph_out = repo_path / project.graphify_out / "graph.json"
        mode = "update" if graph_out.exists() else "extract"
        registry = load_project_registry()
        project_ref = update_project_status(registry, project.path, status="indexing")
        save_project_registry(registry)

        try:
            proc = await asyncio.create_subprocess_exec(
                python,
                *self._build_extract_args(project, mode),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._extract_env(),
            )
            stdout, stderr = await proc.communicate()
        except Exception as exc:
            project_ref = update_project_status(
                registry, project.path, status="error", error_message=str(exc)
            )
            save_project_registry(registry)
            return {"success": False, "error": str(exc)}

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            error = stderr_text or stdout_text or f"graphify {mode} failed"
            project_ref = update_project_status(
                registry, project.path, status="error", error_message=error
            )
            save_project_registry(registry)
            return {"success": False, "error": error}

        project_ref.status = "ready"
        project_ref.error_message = ""
        project_ref.last_indexed = datetime.now()
        save_project_registry(registry)
        return {
            "success": True,
            "mode": mode,
            "stdout": stdout_text,
            "stderr": stderr_text,
        }

    async def start_index_project(self, project: GraphifyProject) -> dict[str, Any]:
        """Start indexing *project* in the background.

        Returns immediately with the task status so the admin UI can poll
        progress instead of blocking on a long-running ``graphify extract``.
        """
        existing = self._indexing_tasks.get(project.path)
        if existing is not None and not existing.done():
            return {
                "success": True,
                "status": "already_running",
                "path": project.path,
            }
        task = asyncio.create_task(self._run_index_project(project))
        self._indexing_tasks[project.path] = task
        return {"success": True, "status": "started", "path": project.path}

    async def _run_index_project(self, project: GraphifyProject) -> dict[str, Any]:
        try:
            return await self.index_project(project)
        finally:
            self._indexing_tasks.pop(project.path, None)

    def get_index_task_status(self, path: str) -> dict[str, Any] | None:
        """Return in-progress status for a background indexing task."""
        task = self._indexing_tasks.get(path)
        if task is None:
            return None
        if task.done():
            try:
                result = task.result()
            except Exception as exc:
                return {"path": path, "status": "error", "error_message": str(exc)}
            status = "ready" if result.get("success") else "error"
            return {
                "path": path,
                "status": status,
                "result": result,
                "error_message": result.get("error", ""),
            }
        return {"path": path, "status": "indexing"}

    async def _auto_index_projects(self) -> None:
        registry = load_project_registry()
        for project in registry.projects:
            if project.status in {"missing", "stale", "error"}:
                await self.index_project(project)

    async def _wait_for_ready(self, timeout: float = 15.0) -> bool:
        if not self._base_url:
            return False
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    resp = await self._probe_mcp(client)
                    if resp.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.4)
        return False

    def _mcp_probe_headers(self) -> dict[str, str]:
        """Return headers for the MCP initialize probe, with auth when configured."""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._settings.graphify_api_key:
            headers["Authorization"] = f"Bearer {self._settings.graphify_api_key}"
        return headers

    async def _probe_mcp(self, client: httpx.AsyncClient) -> httpx.Response:
        """POST an MCP initialize request to the Graphify ``/mcp`` endpoint."""
        return await client.post(
            f"{self._base_url}/mcp",
            json=_MCP_INITIALIZE_BODY,
            headers=self._mcp_probe_headers(),
        )

    def _resolve_llm_api_key(self, backend: str) -> str:
        """Return the API key for *backend*, reusing a Claude Unbound provider key.

        ``GRAPHIFY_LLM_API_KEY`` wins; when it is empty we fall back to the matching
        provider key already configured on the Providers tab (cloudflare/gemini/
        deepseek/kimi), so the user does not re-enter it.
        """
        key = self._settings.graphify_llm_api_key.strip()
        if key:
            return key
        attr = _GRAPHIFY_PROVIDER_KEY_FALLBACK.get(backend)
        if attr:
            return getattr(self._settings, attr, "").strip()
        return ""

    def _cloudflare_openai_base(self) -> str:
        """Return the Cloudflare Workers AI OpenAI-compatible base URL.

        Honours an explicit ``CLOUDFLARE_AI_BASE_URL`` override; otherwise composes
        ``https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1`` from
        the configured account id — the same endpoint Claude Unbound's own
        Cloudflare provider speaks.
        """
        override = self._settings.cloudflare_ai_base_url.strip()
        if override:
            return override
        account = self._settings.cloudflare_ai_account_id.strip()
        return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1"

    def _extract_env(self) -> dict[str, str]:
        """Build the environment for ``graphify extract``/``update`` subprocesses.

        Inherits the parent environment and injects the configured LLM backend's
        credentials so the semantic pass over docs/PDFs/images and community naming
        can run. For ``cloudflare`` we redirect graphify's ``openai`` backend at the
        Cloudflare OpenAI-compatible endpoint via ``OPENAI_BASE_URL`` (graphify has
        no native cloudflare backend). The ``GRAPHIFY_API_KEY`` transport auth is
        irrelevant to the indexer.
        """
        env = os.environ.copy()
        backend = self._settings.graphify_llm_backend.strip().lower()
        if not backend:
            return env
        api_key = self._resolve_llm_api_key(backend)
        if backend == "cloudflare":
            env["OPENAI_API_KEY"] = api_key
            env["OPENAI_BASE_URL"] = self._cloudflare_openai_base()
            model = self._settings.graphify_llm_model.strip()
            if model:
                env["GRAPHIFY_OPENAI_MODEL"] = model
            return env
        if backend == "lmstudio":
            # LM Studio serves an OpenAI-compatible API; graphify has no native
            # lmstudio backend so we ride its ``openai`` path via OPENAI_BASE_URL.
            # LM Studio does not require a real API key — the OpenAI SDK needs a
            # non-empty string to initialise.
            env["OPENAI_API_KEY"] = api_key or "lm-studio"
            env["OPENAI_BASE_URL"] = self._settings.lm_studio_base_url.strip()
            model = self._settings.graphify_llm_model.strip()
            if model:
                env["GRAPHIFY_OPENAI_MODEL"] = model
            return env
        env_key = _GRAPHIFY_LLM_ENV_KEYS.get(backend)
        if env_key and api_key:
            env[env_key] = api_key
        return env

    def _build_extract_args(self, project: GraphifyProject, mode: str) -> list[str]:
        """Return the ``graphify <mode> <path>`` argv after the python interpreter.

        ``--backend``/``--model`` apply only to ``extract`` (``update`` is code-only
        by nature). ``--backend`` is passed explicitly so graphify's
        ``detect_backend()`` precedence (gemini→kimi→claude→openai→…) cannot be
        shadowed by a stray key inherited from the parent environment; ``cloudflare``
        maps to graphify's ``openai`` backend.
        """
        args: list[str] = ["-m", "graphify", mode, project.path]
        if mode != "extract":
            return args
        if self._settings.graphify_code_only:
            args.append("--code-only")
            return args
        backend = self._settings.graphify_llm_backend.strip().lower()
        if backend:
            args.extend(["--backend", _GRAPHIFY_BACKEND_ALIAS.get(backend, backend)])
            model = self._settings.graphify_llm_model.strip()
            if model:
                args.extend(["--model", model])
        return args

    async def _ensure_graphify_llm_extra(self, python: str) -> None:
        """Install the LLM SDK the configured backend imports into the graphify venv.

        The isolated venv is created with only ``graphifyy[mcp]`` (no ``openai`` or
        ``anthropic``), so every cloud backend would raise ``ImportError`` mid-extract.
        OpenAI-compatible backends (cloudflare/openai/gemini/kimi/deepseek/ollama) need
        the ``openai`` package; ``claude`` needs ``anthropic``. ``azure``/``bedrock``/
        ``claude-cli`` are out of scope for v1 (boto3/CLI) and are left untouched.
        No-op for code-only indexing or an unset backend.
        """
        backend = self._settings.graphify_llm_backend.strip().lower()
        if self._settings.graphify_code_only or not backend:
            return
        if backend in _GRAPHIFY_OPENAI_SDK_BACKENDS:
            module, extra = "openai", _GRAPHIFY_OPENAI_EXTRA
        else:
            extra = _GRAPHIFY_LLM_EXTRAS.get(backend)
            module = extra
            if not module:
                return
        if _is_module_importable(python, module):
            return
        logger.info(
            "GRAPHIFY_MANAGER: installing graphifyy[{}] into venv for backend {}",
            extra,
            backend,
        )
        proc = await asyncio.create_subprocess_exec(
            _pip_path(python),
            "install",
            "--quiet",
            f"graphifyy[{extra}]",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to install graphifyy[{extra}] for backend {backend}: "
                f"{stderr.decode('utf-8', errors='replace')}"
            )

    def _start_watcher(self) -> None:
        if not getattr(self._settings, "graphify_auto_reindex", False):
            return
        try:
            from .watcher import GraphifyProjectWatcher
        except Exception:
            logger.warning("GRAPHIFY_MANAGER: watcher import failed")
            return
        self._watcher = GraphifyProjectWatcher(self)
        self._watcher.start()

    async def _stop_watcher(self) -> None:
        watcher = self._watcher
        self._watcher = None
        if watcher is None:
            return
        try:
            await watcher.stop()
        except Exception as exc:
            logger.warning(
                "GRAPHIFY_MANAGER: watcher stop failed: {}: {}",
                type(exc).__name__,
                exc,
            )

    async def _remove_backend_silently(self) -> None:
        try:
            unregister_graphify_claude_server()
        except Exception as exc:
            logger.warning(
                "GRAPHIFY_MANAGER: failed to unregister Claude Code MCP server: {}: {}",
                type(exc).__name__,
                exc,
            )


def _is_module_importable(python: str, module: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError, OSError:
        return False
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def _is_graphify_importable(python: str) -> bool:
    return _is_module_importable(python, "graphify")


def _pip_path(python: str) -> str:
    """Return the pip executable sitting next to *python* in a venv."""
    return str(
        Path(python).parent / ("pip.exe" if sys.platform.startswith("win") else "pip")
    )


def _venv_python_path(venv_dir: Path) -> str:
    bin_dir = venv_dir / ("Scripts" if sys.platform.startswith("win") else "bin")
    exe = "python.exe" if sys.platform.startswith("win") else "python"
    return str(bin_dir / exe)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _directory_size(path: Path) -> int:
    """Return the total byte size of *path*, following directories recursively."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                total += _directory_size(Path(entry.path))
            else:
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def _format_bytes(n: int) -> str:
    """Return a human-readable size string for *n* bytes."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


async def _ensure_graphify_venv(venv_dir: Path) -> str:
    """Create an isolated venv and install ``graphifyy[mcp]`` if missing."""
    python = _venv_python_path(venv_dir)
    if _is_graphify_importable(python):
        return python

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    logger.info("GRAPHIFY_MANAGER: creating isolated venv at {}", venv_dir)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "venv",
        str(venv_dir),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        decoded = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to create Graphify venv: {decoded}")

    pip = _pip_path(python)
    logger.info("GRAPHIFY_MANAGER: installing {} into isolated venv", _GRAPHIFY_PACKAGE)
    proc = await asyncio.create_subprocess_exec(
        pip,
        "install",
        "--quiet",
        _GRAPHIFY_PACKAGE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to install graphifyy: {stderr.decode('utf-8', errors='replace')}"
        )

    return python
