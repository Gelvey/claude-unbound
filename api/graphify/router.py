"""Helpers for restarting the MCP router after backend config changes."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from api.mcp_config import _parse_jsonrpc_results, _send_jsonrpc_async, load_mcp_config


def mcp_scripts_dir() -> Path:
    """Return the directory containing the MCP start/stop scripts."""
    return Path(__file__).resolve().parents[2] / "scripts" / "mcp"


def _expand_router_socket(socket_path: str) -> str:
    """Expand leading ``~`` in the router socket path."""
    if socket_path.startswith("~"):
        return socket_path.replace("~", str(Path.home()), 1)
    return socket_path


async def reload_mcp_router_async() -> dict[str, Any]:
    """Ask the running MCP router to reload its config via the ``reload_servers`` tool.

    Returns ``{"reloaded": True, ...}`` when the router acknowledges the reload,
    or ``{"reloaded": False, "error": ...}`` when the router is not reachable or
    the reload was rejected. This is faster than a full process restart.
    """
    config, _ = load_mcp_config()
    socket_path = _expand_router_socket(config.router_socket)
    if not Path(socket_path).exists():
        return {"reloaded": False, "error": "router socket not found"}

    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "graphify-manager", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "reload_servers", "arguments": {}},
        },
    ]
    try:
        resp = await _send_jsonrpc_async(socket_path, messages)
    except Exception as exc:
        return {"reloaded": False, "error": f"router communication failed: {exc}"}

    results = _parse_jsonrpc_results(resp)
    if not results:
        return {"reloaded": False, "error": "no response from router"}

    result = results[-1]
    if not isinstance(result, dict) or not result.get("ok"):
        return {
            "reloaded": False,
            "error": result.get("error", "router reload was rejected"),
        }
    return {"reloaded": True, "summary": result}


async def restart_mcp_router_async(
    *,
    script_dir: str | Path | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Stop then start the MCP router so config changes are picked up.

    The start script is intentionally backgrounded so this coroutine does not
    block until the router exits (it would wait forever).  A small post-start
    probe confirms the Unix socket exists before returning.
    """
    scripts = Path(script_dir) if script_dir else mcp_scripts_dir()
    stop_script = scripts / "stop_mcp.sh"
    start_script = scripts / "start_mcp.sh"

    if not stop_script.is_file() or not start_script.is_file():
        logger.warning(
            "MCP router scripts not found at {} ({}); cannot restart automatically",
            stop_script,
            start_script,
        )
        return {"restarted": False, "error": "MCP router scripts not found"}

    # Run stop first, best effort.
    try:
        stop_proc = await asyncio.create_subprocess_exec(
            "bash",
            str(stop_script),
            "--quiet",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(stop_proc.wait(), timeout=timeout_s)
        except TimeoutError:
            _kill_proc_tree(stop_proc.pid)
    except FileNotFoundError:
        logger.warning("bash not available; cannot stop MCP router")
    except Exception as exc:
        logger.warning("Failed to stop MCP router: {}: {}", type(exc).__name__, exc)

    # Start in a background subprocess without waiting on the script's wait loop.
    try:
        with open(os.devnull, "w") as devnull:
            subprocess.Popen(
                ["bash", str(start_script)],
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )
    except FileNotFoundError:
        return {"restarted": False, "error": "bash not available"}
    except Exception as exc:
        return {
            "restarted": False,
            "error": f"Failed to start MCP router: {exc}",
        }

    return {"restarted": True}


def _kill_proc_tree(pid: int | None) -> None:
    if pid is None:
        return
    with contextlib.suppress(ProcessLookupError, OSError):
        os.kill(pid, 15)
