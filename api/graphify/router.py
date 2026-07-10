"""Helpers for restarting the MCP router after backend config changes."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger


def mcp_scripts_dir() -> Path:
    """Return the directory containing the MCP start/stop scripts."""
    return Path(__file__).resolve().parents[2] / "scripts" / "mcp"


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
