"""Tests for Graphify MCP backend config mutation."""

from __future__ import annotations

from pathlib import Path

from api.graphify.mcp_backend import (
    add_graphify_mcp_backend,
    build_graphify_mcp_backend,
    remove_graphify_mcp_backend,
)
from api.mcp_config import load_mcp_config


def test_build_graphify_mcp_backend_includes_api_key() -> None:
    backend = build_graphify_mcp_backend(port=9876, api_key="secret")

    assert backend["name"] == "graphify"
    assert backend["type"] == "http"
    assert backend["port"] == 9876
    assert backend["url"] == "http://127.0.0.1:9876/mcp"
    assert backend["headers"] == {"Authorization": "Bearer secret"}


def test_build_graphify_mcp_backend_omits_auth_when_no_key() -> None:
    backend = build_graphify_mcp_backend(port=9876, api_key="")

    assert backend["headers"] == {}


def test_add_graphify_mcp_backend_creates_file(
    graphify_tmp_home: Path,
) -> None:
    add_graphify_mcp_backend(9876, "secret")

    config, path = load_mcp_config()
    assert path.exists()
    assert "graphify" in config.servers
    assert config.servers["graphify"].url == "http://127.0.0.1:9876/mcp"


def test_add_graphify_mcp_backend_is_idempotent(
    graphify_tmp_home: Path,
) -> None:
    add_graphify_mcp_backend(9876, "secret")
    add_graphify_mcp_backend(9877, "secret2")

    config, _ = load_mcp_config()
    assert len(config.servers) == 1
    assert config.servers["graphify"].port == 9877
    assert config.servers["graphify"].headers == {"Authorization": "Bearer secret2"}


def test_remove_graphify_mcp_backend(graphify_tmp_home: Path) -> None:
    add_graphify_mcp_backend(9876, "secret")
    remove_graphify_mcp_backend()

    config, _ = load_mcp_config()
    assert "graphify" not in config.servers


def test_remove_graphify_mcp_backend_is_idempotent(
    graphify_tmp_home: Path,
) -> None:
    remove_graphify_mcp_backend()
    config, _ = load_mcp_config()
    assert "graphify" not in config.servers
