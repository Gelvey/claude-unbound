"""Tests for scripts/mcp/mcp_router.py — per-connection isolation and
``notifications/tools/list_changed`` emission.

These exercise the router's MCP ``Server`` handlers directly (via
``request_handlers``) with a mock session so we can assert the notification
fires on the right state transitions without needing a live backend SSE
connection. The router module is loaded by path (it lives in ``scripts/mcp/``
which is not on the test pythonpath) so each test gets a fresh module with
its own ``_CONFIG_PATH`` global.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import PropertyMock, patch

import pytest
from mcp import types


def _load_router_module(module_name: str = "mcp_router_under_test") -> Any:
    """Load scripts/mcp/mcp_router.py as a fresh module (not on sys.path)."""
    repo_root = Path(__file__).resolve().parents[2]
    router_path = repo_root / "scripts" / "mcp" / "mcp_router.py"
    spec = importlib.util.spec_from_file_location(module_name, router_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_config(path: Path, servers: dict[str, Any]) -> None:
    path.write_text(json.dumps({"servers": servers}))


def _sse_cfg(url: str) -> dict[str, Any]:
    return {"type": "sse", "url": url}


class _MockSession:
    """Records send_tool_list_changed() calls without a real MCP transport."""

    def __init__(self) -> None:
        self.tool_list_changed_calls = 0

    async def send_tool_list_changed(self) -> None:
        self.tool_list_changed_calls += 1


@contextmanager
def _mock_request_ctx(server: Any, session: _MockSession) -> Any:
    """Patch Server.request_context to return a session-bearing object.

    The router emits the notification via
    ``server.request_context.session.send_tool_list_changed()``. Patching the
    property (rather than setting the ``request_ctx`` ContextVar) avoids
    constructing a ``RequestContext`` whose ``session`` would have to satisfy
    the SDK's ``BaseSession`` type bound.
    """
    mock_ctx = SimpleNamespace(session=session)
    with patch.object(
        type(server),
        "request_context",
        new_callable=PropertyMock,
        return_value=mock_ctx,
    ):
        yield


def _call_tool_request(
    name: str, arguments: dict[str, Any] | None = None
) -> types.CallToolRequest:
    return types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )


def _list_tools_request() -> types.ListToolsRequest:
    return types.ListToolsRequest(method="tools/list")


def _result_text(server_result: types.ServerResult) -> str:
    return server_result.root.content[0].text


def _make_active(backend: Any) -> None:
    """Mark a Backend as activated without a real SSE session.

    ``_deactivate`` calls ``shutdown.set()`` then awaits ``done``; pre-setting
    the future's result lets that await return immediately so the test does
    not need a running ``_session_owner`` task.
    """
    loop = asyncio.get_running_loop()
    backend._session = object()  # truthy sentinel
    backend._shutdown = asyncio.Event()
    backend._owner_done = loop.create_future()
    backend._owner_done.set_result(None)
    backend.tools = {
        "fake_tool": types.Tool(
            name="fake_tool", description="x", inputSchema={"type": "object"}
        )
    }


# ---------------------------------------------------------------------------
# load_config: per-connection isolation starts here
# ---------------------------------------------------------------------------


def test_load_config_returns_independent_backend_objects(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    b1, _ = m.load_config(cfg)
    b2, _ = m.load_config(cfg)
    assert b1["stripe"] is not b2["stripe"]
    assert b1["stripe"].name == b2["stripe"].name


# ---------------------------------------------------------------------------
# Per-connection isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_connection_isolation_activations_do_not_leak(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends_a, _ = m.load_config(cfg)
    backends_b, _ = m.load_config(cfg)
    server_a = m._build_server(backends_a)
    server_b = m._build_server(backends_b)

    # Simulate server A activating stripe: register a tool on A's backend only.
    backends_a["stripe"].tools = {
        "list_customers": types.Tool(
            name="list_customers", description="d", inputSchema={"type": "object"}
        )
    }

    names_a = [
        t.name
        for t in (
            await server_a.request_handlers[types.ListToolsRequest](
                _list_tools_request()
            )
        ).root.tools
    ]
    names_b = [
        t.name
        for t in (
            await server_b.request_handlers[types.ListToolsRequest](
                _list_tools_request()
            )
        ).root.tools
    ]

    assert "stripe__list_customers" in names_a
    assert "stripe__list_customers" not in names_b
    # Both still advertise the control tools regardless of activations.
    assert "list_servers" in names_a and "list_servers" in names_b


# ---------------------------------------------------------------------------
# send_tool_list_changed notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_server_emits_notification_on_active_backend(
    tmp_path: Path,
) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    _make_active(backends["stripe"])
    server = m._build_server(backends)
    session = _MockSession()
    with _mock_request_ctx(server, session):
        handler = server.request_handlers[types.CallToolRequest]
        res = await handler(_call_tool_request("deactivate_server", {"name": "stripe"}))
    data = json.loads(_result_text(res))
    assert data["ok"] is True
    assert session.tool_list_changed_calls == 1
    # _deactivate actually tore the backend down.
    assert backends["stripe"]._session is None
    assert backends["stripe"].tools == {}


@pytest.mark.asyncio
async def test_deactivate_server_no_notification_when_already_inactive(
    tmp_path: Path,
) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    server = m._build_server(backends)
    session = _MockSession()
    with _mock_request_ctx(server, session):
        handler = server.request_handlers[types.CallToolRequest]
        res = await handler(_call_tool_request("deactivate_server", {"name": "stripe"}))
    data = json.loads(_result_text(res))
    assert data["ok"] is True
    assert data["already_inactive"] is True
    assert session.tool_list_changed_calls == 0


@pytest.mark.asyncio
async def test_use_server_already_active_no_notification(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    _make_active(backends["stripe"])
    server = m._build_server(backends)
    session = _MockSession()
    with _mock_request_ctx(server, session):
        handler = server.request_handlers[types.CallToolRequest]
        res = await handler(_call_tool_request("use_server", {"name": "stripe"}))
    data = json.loads(_result_text(res))
    assert data["ok"] is True
    assert data["already_active"] is True
    assert session.tool_list_changed_calls == 0


@pytest.mark.asyncio
async def test_reload_emits_notification_when_backends_change(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    server = m._build_server(backends)
    m._CONFIG_PATH = cfg
    session = _MockSession()
    with _mock_request_ctx(server, session):
        # Add a backend on disk so reload sees an actual change.
        _write_config(
            cfg,
            {
                "stripe": _sse_cfg("http://127.0.0.1:1/sse"),
                "clerk": _sse_cfg("http://127.0.0.1:2/sse"),
            },
        )
        handler = server.request_handlers[types.CallToolRequest]
        res = await handler(_call_tool_request("reload_servers", {}))
    m._CONFIG_PATH = None
    data = json.loads(_result_text(res))
    assert data["ok"] is True
    assert "clerk" in data["added"]
    assert session.tool_list_changed_calls == 1


@pytest.mark.asyncio
async def test_reload_no_notification_when_unchanged(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    server = m._build_server(backends)
    m._CONFIG_PATH = cfg
    session = _MockSession()
    with _mock_request_ctx(server, session):
        handler = server.request_handlers[types.CallToolRequest]
        res = await handler(_call_tool_request("reload_servers", {}))
    m._CONFIG_PATH = None
    data = json.loads(_result_text(res))
    assert data["ok"] is True
    assert data["added"] == [] and data["updated"] == [] and data["removed"] == []
    assert session.tool_list_changed_calls == 0


# ---------------------------------------------------------------------------
# Disconnect cleanup: _deactivate is the primitive the _handle_client finally
# block calls for each active backend on disconnect. Verify it fully tears a
# backend down so the per-connection cleanup loop leaves no leaked session.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_fully_tears_down_active_backend(tmp_path: Path) -> None:
    m = _load_router_module()
    cfg = tmp_path / "c.json"
    _write_config(cfg, {"stripe": _sse_cfg("http://127.0.0.1:1/sse")})
    backends, _ = m.load_config(cfg)
    _make_active(backends["stripe"])
    result = await m._deactivate("stripe", backends)
    assert result["ok"] is True
    b = backends["stripe"]
    assert b._session is None
    assert b._shutdown is None
    assert b._owner_done is None
    assert b._owner_task is None
    assert b.tools == {}
