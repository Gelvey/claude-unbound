"""Tests for Graphify MCP router reload helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.graphify.router import reload_mcp_router_async


@pytest.fixture
def router_socket(graphify_tmp_home: Path) -> Path:
    """Create a fake router socket on disk and override the config path."""
    socket_path = graphify_tmp_home / "router.sock"
    socket_path.write_text("")
    return socket_path


@pytest.mark.asyncio
async def test_reload_mcp_router_reports_missing_socket(
    graphify_tmp_home: Path,
) -> None:
    with patch("api.graphify.router.load_mcp_config") as load_config:
        load_config.return_value = (_MockConfig("/no/such/router.sock"), None)
        result = await reload_mcp_router_async()

    assert result["reloaded"] is False
    assert "socket" in result["error"].lower()


@pytest.mark.asyncio
async def test_reload_mcp_router_succeeds(router_socket: Path) -> None:
    with (
        patch("api.graphify.router.load_mcp_config") as load_config,
        patch(
            "api.graphify.router._send_jsonrpc_async",
            new_callable=AsyncMock,
            return_value=b'{"jsonrpc":"2.0","id":3,"result":{"ok":true}}',
        ),
        patch(
            "api.graphify.router._parse_jsonrpc_results",
            return_value=[{"ok": True}],
        ),
    ):
        load_config.return_value = (_MockConfig(str(router_socket)), None)
        result = await reload_mcp_router_async()

    assert result["reloaded"] is True


@pytest.mark.asyncio
async def test_reload_mcp_router_reports_rejected_reload(router_socket: Path) -> None:
    with (
        patch("api.graphify.router.load_mcp_config") as load_config,
        patch(
            "api.graphify.router._send_jsonrpc_async",
            new_callable=AsyncMock,
            return_value=b'{"jsonrpc":"2.0","id":3,"result":{"ok":false,"error":"bad config"}}',
        ),
        patch(
            "api.graphify.router._parse_jsonrpc_results",
            return_value=[{"ok": False, "error": "bad config"}],
        ),
    ):
        load_config.return_value = (_MockConfig(str(router_socket)), None)
        result = await reload_mcp_router_async()

    assert result["reloaded"] is False
    assert "bad config" in result["error"]


@pytest.mark.asyncio
async def test_reload_mcp_router_reports_communication_error(
    router_socket: Path,
) -> None:
    with (
        patch("api.graphify.router.load_mcp_config") as load_config,
        patch(
            "api.graphify.router._send_jsonrpc_async",
            new_callable=AsyncMock,
            side_effect=ConnectionRefusedError("refused"),
        ),
    ):
        load_config.return_value = (_MockConfig(str(router_socket)), None)
        result = await reload_mcp_router_async()

    assert result["reloaded"] is False
    assert "refused" in result["error"]


class _MockConfig:
    def __init__(self, router_socket: str) -> None:
        self.router_socket = router_socket
