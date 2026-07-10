"""Live smoke test: boot the real ``graphify.serve`` and probe ``/mcp``.

Skips when ``graphifyy`` is not importable, so CI without the ``graphify`` extra
still passes. Run locally with the isolated venv present at
``~/.fcc/graphify/venv`` (created by the Admin UI Setup button) or with
``graphifyy[mcp]`` installed in the test environment.

This is the live coverage the integration plan promised: it proves the
readiness/health probe actually works against a real Graphify Streamable HTTP
server (which rejects plain ``GET /mcp`` with 406).
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from api.graphify.manager import _MCP_INITIALIZE_BODY, _parse_sse_data


def _graphify_python() -> str | None:
    """Return a Python interpreter that can ``import graphify``, else None."""
    candidates = [sys.executable]
    venv_python = Path.home() / ".fcc" / "graphify" / "venv" / "bin" / "python"
    if venv_python.exists():
        candidates.append(str(venv_python))
    for python in candidates:
        try:
            proc = subprocess.run(
                [python, "-c", "import graphify"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except FileNotFoundError, OSError, subprocess.TimeoutExpired:
            continue
        if proc.returncode == 0:
            return python
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_GRAPHIFY_PYTHON = _graphify_python()


@pytest.mark.asyncio
@pytest.mark.skipif(_GRAPHIFY_PYTHON is None, reason="graphifyy not importable")
async def test_live_graphify_serve_probes_healthy(tmp_path: Path) -> None:
    python = _GRAPHIFY_PYTHON
    assert python is not None
    port = _free_port()
    proc = await asyncio.create_subprocess_exec(
        python,
        "-m",
        "graphify.serve",
        "--transport",
        "http",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        cwd=str(tmp_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        data: dict[str, object] | None = None
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Wait for the server via the real readiness probe (POST initialize).
            ready = False
            for _ in range(60):
                try:
                    resp = await client.post(
                        url, json=_MCP_INITIALIZE_BODY, headers=headers
                    )
                    if resp.status_code == 200:
                        ready = True
                        data = _parse_sse_data(resp.text)
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.25)

            assert ready, "graphify.serve did not become ready via POST initialize"

            # A plain GET must NOT yield 200: the Streamable HTTP server returns
            # 406 ("Client must accept text/event-stream"). This is the bug the
            # readiness/health probe had to fix — prove it holds on the real server.
            get_resp = await client.get(url)
            assert get_resp.status_code == 406

        assert isinstance(data, dict)
        result = data["result"]
        assert isinstance(result, dict)
        server_info = result["serverInfo"]
        assert isinstance(server_info, dict)
        assert server_info["name"] == "graphify"
    finally:
        proc.terminate()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
