"""Graphify lifecycle manager."""

from __future__ import annotations

import asyncio
import contextlib
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

from .config import GraphifyProject
from .mcp_backend import add_graphify_mcp_backend, remove_graphify_mcp_backend
from .paths import graphify_venv_dir
from .projects import (
    load_project_registry,
    save_project_registry,
    update_project_status,
)
from .router import restart_mcp_router_async

_GRAPHIFY_PACKAGE = "graphifyy[mcp]"


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

        add_graphify_mcp_backend(port, self._settings.graphify_api_key)

        env = os.environ.copy()
        env["GRAPHIFY_API_KEY"] = self._settings.graphify_api_key or ""
        try:
            self._process = await asyncio.create_subprocess_exec(
                python,
                "-m",
                "graphify.serve",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
        except Exception as exc:
            self._last_error = str(exc)
            await self._remove_backend_silently()
            return False

        if await self._wait_for_ready():
            self._last_error = None
            logger.info(
                "GRAPHIFY_MANAGER: started port={} python={}",
                port,
                python,
            )
            if self._settings.graphify_auto_index_on_start:
                await self._auto_index_projects()
            return True

        self._last_error = "Graphify health check timed out"
        await self.stop()
        return False

    async def stop(self) -> None:
        """Stop Graphify and remove its MCP backend."""
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
        """Probe the Graphify ``/mcp`` endpoint."""
        if not self._base_url:
            return {"status": "not_configured", "error": "Graphify is not running"}
        url = f"{self._base_url}/mcp"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            return {"status": "unreachable", "error": str(exc)}
        try:
            data = resp.json()
        except Exception:
            data = None
        if resp.status_code == 200:
            return {"status": "healthy", "http_status": resp.status_code, "data": data}
        return {
            "status": "unhealthy",
            "http_status": resp.status_code,
            "data": data,
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
        graph_out = Path(project.path) / project.graphify_out / "graph.json"
        mode = "update" if graph_out.exists() else "extract"
        registry = load_project_registry()
        project_ref = update_project_status(registry, project.path, status="indexing")
        save_project_registry(registry)

        try:
            proc = await asyncio.create_subprocess_exec(
                python,
                "-m",
                "graphify",
                mode,
                project.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
                    resp = await client.get(f"{self._base_url}/mcp")
                    if resp.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.4)
        return False

    async def _remove_backend_silently(self) -> None:
        try:
            remove_graphify_mcp_backend()
            await restart_mcp_router_async()
        except Exception as exc:
            logger.warning(
                "GRAPHIFY_MANAGER: failed to remove MCP backend: {}: {}",
                type(exc).__name__,
                exc,
            )


def _is_graphify_importable(python: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", "import graphify"],
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


def _venv_python_path(venv_dir: Path) -> str:
    bin_dir = venv_dir / ("Scripts" if sys.platform.startswith("win") else "bin")
    exe = "python.exe" if sys.platform.startswith("win") else "python"
    return str(bin_dir / exe)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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
        raise RuntimeError(
            f"Failed to create Graphify venv: {stderr.decode('utf-8', errors='replace')}"
        )

    pip = str(
        Path(python).parent / ("pip.exe" if sys.platform.startswith("win") else "pip")
    )
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
