"""Server lifecycle mixin for :class:`GraphifyManager`.

Extracted from ``manager.py`` — subprocess management, venv setup, port
adoption, readiness probes, and watcher lifecycle.  Methods are defined on
this mixin and inherited by ``GraphifyManager``; ``self`` is annotated as
``GraphifyManager`` so the type checker sees the full combined-class interface
(attributes set in ``__init__``, methods provided by ``CoordinatorMixin``).

Names that tests patch via ``api.graphify.manager.X`` (e.g.
``_is_graphify_importable``, ``register_graphify_claude_server``) are routed
through the manager module at call time via ``_manager`` so that
``mock.patch("api.graphify.manager.X")`` takes effect even though the calling
code lives in this mixin module.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from .graphify_helpers import _ensure_graphify_venv, _venv_python_path
from .graphify_probes import _MCP_INITIALIZE_BODY
from .paths import graphify_venv_dir

if TYPE_CHECKING:
    from .manager import GraphifyManager

# The manager module is always in ``sys.modules`` by the time any method is
# called (it imported this mixin).  We bind it eagerly at import time — the
# partially-loaded module object is fine; attributes are only read at call
# time, long after ``manager.py`` has finished loading.
import api.graphify.manager as _manager  # circular at import, safe at call


class ProcessMixin:
    """Server lifecycle methods.  Mixed into :class:`GraphifyManager`."""

    def _resolve_python(self: GraphifyManager) -> str:
        """Return the Python interpreter that should run graphify commands."""
        if self._python_path:
            return self._python_path
        configured = self._settings.graphify_python_path.strip()
        if configured:
            return configured
        if _manager._is_graphify_importable(sys.executable):
            return sys.executable
        venv_python = _venv_python_path(graphify_venv_dir())
        if _manager._is_graphify_importable(venv_python):
            return venv_python
        return sys.executable

    async def setup(
        self: GraphifyManager, *, create_venv: bool = True
    ) -> dict[str, Any]:
        """Ensure graphifyy is available, installing to an isolated venv if needed."""
        python = self._resolve_python()
        if _manager._is_graphify_importable(python):
            self._python_path = python
            return {
                "ready": True,
                "python": python,
                "method": "existing" if python == sys.executable else "venv",
            }

        if create_venv and python == sys.executable:
            venv_python = await _ensure_graphify_venv(graphify_venv_dir())
            if _manager._is_graphify_importable(venv_python):
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

    async def start(self: GraphifyManager) -> bool:
        """Start the Graphify HTTP MCP server."""
        if self.is_running:
            return True

        setup_result = await self.setup(create_venv=True)
        if not setup_result["ready"]:
            self._last_error = setup_result.get("error", "Graphify not available")
            return False

        python = setup_result["python"]
        port = self._settings.graphify_server_port or _manager._find_free_port()

        # Adoption: if a Graphify server is already healthy on the target port,
        # attach to it rather than spawning a duplicate. The server may be left
        # over from a forcefully-killed prior fcc-server (which could not run
        # its stop()), or owned by a concurrent fcc-server instance. The fixed
        # GRAPHIFY_SERVER_PORT makes the target port stable across restarts so
        # adoption is reliable. An adopted server is NOT ours to kill, and a
        # later stop() will not unregister it — so a short-lived sibling
        # fcc-server instance (e.g. a transient restart) cannot tear down the
        # graphify a long-lived instance depends on.
        if await _manager._probe_graphify_port(port, self._settings.graphify_api_key):
            self._port = port
            self._base_url = f"http://127.0.0.1:{port}"
            self._python_path = python
            self._adopted = True
            self._owns_process = False
            _manager.register_graphify_claude_server(
                port, self._settings.graphify_api_key
            )
            self._last_error = None
            logger.info("GRAPHIFY_MANAGER: adopted existing graphify on port {}", port)
            self._start_index_worker()
            self._start_watcher()
            if self._settings.graphify_auto_index_on_start:
                await self._auto_index_projects()
            return True

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
        # We spawned it, so we own it — claim ownership immediately so the
        # readiness-failure cleanup `stop()` below actually kills the
        # half-spawned process instead of leaking it.
        self._owns_process = True
        self._adopted = False

        if not await self._wait_for_ready():
            self._last_error = "Graphify health check timed out"
            await self.stop()
            return False

        # Server is confirmed up: register it as a sibling Claude Code MCP
        # server (in ~/.claude.json mcpServers, alongside mcp-router). Graphify
        # is not a backend inside the MCP Router — Claude Code connects to it
        # directly over loopback HTTP.
        _manager.register_graphify_claude_server(port, self._settings.graphify_api_key)

        self._last_error = None
        logger.info(
            "GRAPHIFY_MANAGER: started port={} python={}",
            port,
            python,
        )
        self._start_index_worker()
        self._start_watcher()
        if self._settings.graphify_auto_index_on_start:
            await self._auto_index_projects()
        return True

    async def stop(self: GraphifyManager) -> None:
        """Stop Graphify and remove its MCP backend if this manager owns it.

        An adopted server (one we found already running on the target port,
        owned by another instance) is left untouched: we do not kill the
        process and we do not remove the ``~/.claude.json`` entry. This is the
        guard that keeps a short-lived sibling fcc-server instance from
        unregistering graphify that a long-lived instance registered.
        """
        await self._stop_watcher()
        await self._drain_index_queue()
        process = self._process
        owns = self._owns_process
        self._process = None
        self._adopted = False
        self._owns_process = False
        if owns and process and process.returncode is None:
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
        if owns:
            await self._remove_backend_silently()
        logger.info("GRAPHIFY_MANAGER: stopped (owned={})", owns)

    async def restart(self: GraphifyManager) -> bool:
        """Restart the Graphify server."""
        await self.stop()
        return await self.start()

    async def _wait_for_ready(self: GraphifyManager, timeout: float = 15.0) -> bool:
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

    def _mcp_probe_headers(self: GraphifyManager) -> dict[str, str]:
        """Return headers for the MCP initialize probe, with auth when configured."""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._settings.graphify_api_key:
            headers["Authorization"] = f"Bearer {self._settings.graphify_api_key}"
        return headers

    async def _probe_mcp(
        self: GraphifyManager, client: httpx.AsyncClient
    ) -> httpx.Response:
        """POST an MCP initialize request to the Graphify ``/mcp`` endpoint."""
        return await client.post(
            f"{self._base_url}/mcp",
            json=_MCP_INITIALIZE_BODY,
            headers=self._mcp_probe_headers(),
        )

    async def _remove_backend_silently(self: GraphifyManager) -> None:
        try:
            _manager.unregister_graphify_claude_server()
        except Exception as exc:
            logger.warning(
                "GRAPHIFY_MANAGER: failed to unregister Claude Code MCP server: {}: {}",
                type(exc).__name__,
                exc,
            )

    def _start_watcher(self: GraphifyManager) -> None:
        if not getattr(self._settings, "graphify_auto_reindex", False):
            return
        try:
            from .watcher import GraphifyProjectWatcher
        except Exception:
            logger.warning("GRAPHIFY_MANAGER: watcher import failed")
            return
        self._watcher = GraphifyProjectWatcher(self)
        self._watcher.start()

    async def _stop_watcher(self: GraphifyManager) -> None:
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
