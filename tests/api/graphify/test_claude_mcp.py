"""Tests for the Graphify Claude Code sibling MCP server registration."""

from __future__ import annotations

import json
from pathlib import Path

from api.graphify.claude_mcp import (
    GRAPHIFY_SERVER_NAME,
    build_graphify_server_entry,
    graphify_claude_server_registered,
    register_graphify_claude_server,
    unregister_graphify_claude_server,
)


def _read_servers(home: Path) -> dict:
    return json.loads((home / ".claude.json").read_text())["mcpServers"]


def test_build_entry_includes_auth_when_key_set() -> None:
    entry = build_graphify_server_entry(port=9876, api_key="secret")
    assert entry["type"] == "http"
    assert entry["url"] == "http://127.0.0.1:9876/mcp"
    assert entry["headers"] == {"Authorization": "Bearer secret"}


def test_build_entry_omits_headers_when_no_key() -> None:
    entry = build_graphify_server_entry(port=9876, api_key="")
    assert "headers" not in entry


def test_register_creates_sibling_entry(graphify_tmp_home: Path) -> None:
    result = register_graphify_claude_server(9876, "secret")
    assert result["registered"] is True
    assert result["port"] == 9876
    servers = _read_servers(graphify_tmp_home)
    assert GRAPHIFY_SERVER_NAME in servers
    assert servers[GRAPHIFY_SERVER_NAME]["url"] == "http://127.0.0.1:9876/mcp"
    assert graphify_claude_server_registered() is True


def test_register_preserves_existing_mcp_router_and_top_level_keys(
    graphify_tmp_home: Path,
) -> None:
    path = graphify_tmp_home / ".claude.json"
    existing = {
        "history": ["/some/old/path"],
        "mcpServers": {
            "mcp-router": {"type": "stdio", "command": "/bin/mcp-proxy-tool"},
        },
        "theme": "dark",
    }
    path.write_text(json.dumps(existing))

    register_graphify_claude_server(9876, "")

    data = json.loads(path.read_text())
    assert data["history"] == ["/some/old/path"]
    assert data["theme"] == "dark"
    assert "mcp-router" in data["mcpServers"]
    assert GRAPHIFY_SERVER_NAME in data["mcpServers"]
    assert "headers" not in data["mcpServers"][GRAPHIFY_SERVER_NAME]


def test_register_is_idempotent_and_refreshes_port(graphify_tmp_home: Path) -> None:
    register_graphify_claude_server(9876, "k")
    register_graphify_claude_server(9999, "k")
    servers = _read_servers(graphify_tmp_home)
    assert servers[GRAPHIFY_SERVER_NAME]["url"] == "http://127.0.0.1:9999/mcp"
    # Only one graphify entry.
    assert list(servers).count(GRAPHIFY_SERVER_NAME) == 1


def test_unregister_removes_only_graphify(graphify_tmp_home: Path) -> None:
    path = graphify_tmp_home / ".claude.json"
    path.write_text(
        json.dumps(
            {"mcpServers": {"mcp-router": {"type": "stdio"}, GRAPHIFY_SERVER_NAME: {}}}
        )
    )

    result = unregister_graphify_claude_server()
    assert result["registered"] is False
    servers = _read_servers(graphify_tmp_home)
    assert GRAPHIFY_SERVER_NAME not in servers
    assert "mcp-router" in servers
    assert graphify_claude_server_registered() is False


def test_unregister_when_missing_is_noop(graphify_tmp_home: Path) -> None:
    result = unregister_graphify_claude_server()
    assert result["registered"] is False
    assert graphify_claude_server_registered() is False


def test_registered_false_when_no_claude_json(graphify_tmp_home: Path) -> None:
    assert graphify_claude_server_registered() is False
