"""Tests for async MCP config socket I/O functions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import tempfile
from pathlib import Path

import pytest

from api.mcp_config import (
    _parse_jsonrpc_results,
    _send_jsonrpc_async,
    get_router_status,
)

# ---------------------------------------------------------------------------
# _send_jsonrpc_async tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def short_tmp_path():
    """Return a short-lived temp dir under /tmp to keep AF_UNIX paths under the 104-char macOS limit."""
    d = Path(tempfile.mkdtemp(prefix="t-"))
    yield d
    for f in d.iterdir():
        f.unlink(missing_ok=True)
    d.rmdir()


@pytest.mark.asyncio
async def test_send_jsonrpc_async_returns_response_on_success(
    short_tmp_path: Path,
) -> None:
    """_send_jsonrpc_async sends messages and returns the decoded response."""
    # Create a real Unix socket server for the test
    sock_path = str(short_tmp_path / "t.sock")
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(sock_path)
    server_sock.listen(1)
    server_sock.settimeout(5)

    async def _serverResponder():
        """Accept one connection, read lines, and send JSON-RPC responses."""
        loop = asyncio.get_event_loop()
        conn, _ = await loop.run_in_executor(None, server_sock.accept)
        conn.settimeout(5)

        # Read all incoming lines
        buf = b""
        while buf.count(b"\n") < 4:
            chunk = await loop.run_in_executor(None, conn.recv, 8192)
            if not chunk:
                break
            buf += chunk

        # Send responses for each request
        for i in range(1, 5):
            response = (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": i,
                        "result": {
                            "content": [{"text": json.dumps([{"name": f"server-{i}"}])}]
                        },
                    }
                )
                + "\n"
            )
            await loop.run_in_executor(None, conn.sendall, response.encode())

        conn.close()

    server_task = asyncio.create_task(_serverResponder())

    try:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {}},
        ]
        result = await _send_jsonrpc_async(sock_path, messages)

        # Should contain the response lines
        assert "server-1" in result
        assert "server-4" in result
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task
        server_sock.close()


@pytest.mark.asyncio
async def test_send_jsonrpc_async_handles_missing_socket(tmp_path: Path) -> None:
    """_send_jsonrpc_async raises when the socket path doesn't exist."""
    sock_path = str(tmp_path / "nonexistent.sock")

    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}]
    # Connection to a nonexistent socket raises FileNotFoundError or ConnectionRefusedError
    with pytest.raises((FileNotFoundError, ConnectionRefusedError, OSError)):
        await _send_jsonrpc_async(sock_path, messages)


# ---------------------------------------------------------------------------
# get_router_status tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_router_status_returns_not_running_when_socket_missing(
    tmp_path: Path,
) -> None:
    """get_router_status returns {running: False} when the socket doesn't exist."""
    sock_path = str(tmp_path / "missing.sock")
    result = await get_router_status(sock_path)
    assert result == {"running": False}


@pytest.mark.asyncio
async def test_get_router_status_returns_not_running_on_connection_error(
    tmp_path: Path,
) -> None:
    """get_router_status returns {running: False} when the socket exists but is not connectable."""
    sock_path = str(tmp_path / "nolistener.sock")
    # Create the file so os.path.exists passes, but it's not a real socket
    Path(sock_path).touch()

    result = await get_router_status(sock_path)
    assert result == {"running": False}


# ---------------------------------------------------------------------------
# _parse_jsonrpc_results tests
# ---------------------------------------------------------------------------


def test_parse_jsonrpc_results_extracts_content_text() -> None:
    """_parse_jsonrpc_results parses JSON from result.content[0].text fields."""
    resp = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [
                        {"text": json.dumps([{"name": "server-a", "tool_count": 3}])}
                    ]
                },
            }
        )
        + "\n"
    )
    results = _parse_jsonrpc_results(resp)
    assert len(results) == 1
    assert isinstance(results[0], list)
    assert results[0][0]["name"] == "server-a"


def test_parse_jsonrpc_results_skips_lines_without_result() -> None:
    """_parse_jsonrpc_results skips JSON lines that have no 'result' key."""
    resp = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "oops"}})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"content": [{"text": json.dumps({"ok": True})}]},
            }
        )
        + "\n"
    )
    results = _parse_jsonrpc_results(resp)
    assert len(results) == 1
    assert results[0] == {"ok": True}


def test_parse_jsonrpc_results_empty_string() -> None:
    """_parse_jsonrpc_results returns empty list for empty input."""
    assert _parse_jsonrpc_results("") == []


def test_parse_jsonrpc_results_skips_invalid_json() -> None:
    """_parse_jsonrpc_results skips lines that are not valid JSON."""
    resp = (
        "not json at all\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"text": json.dumps([{"name": "ok"}])}]},
            }
        )
        + "\n"
    )
    results = _parse_jsonrpc_results(resp)
    assert len(results) == 1
