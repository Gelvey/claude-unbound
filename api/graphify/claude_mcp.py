"""Register the local Graphify MCP server as a sibling of the MCP Router.

Graphify is *not* a backend inside the MCP Router (``mcp_config.json``). It is a
standalone Streamable-HTTP MCP server that Claude Code connects to directly, so
Claude Code sees two sibling servers in its own config: ``mcp-router`` and
``graphify``. Claude Code's MCP server list lives in the top-level ``mcpServers``
map of ``~/.claude.json``; this module writes the ``graphify`` entry there
atomically, preserving every other key.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from loguru import logger

GRAPHIFY_SERVER_NAME = "graphify"


def claude_json_path() -> Path:
    """Return the path to the user's ``~/.claude.json`` (resolved lazily)."""
    return Path.home() / ".claude.json"


def _load_claude_json() -> dict[str, Any]:
    """Read ``~/.claude.json``. Missing or malformed → empty dict (never raises)."""
    path = claude_json_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("GRAPHIFY_CLAUDE_MCP: unreadable {}: {}", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically, preserving the existing file mode (default 600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (
        stat.S_IMODE(path.stat().st_mode)
        if path.exists()
        else stat.S_IRUSR | stat.S_IWUSR
    )
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)
    os.chmod(path, mode)


def build_graphify_server_entry(port: int, api_key: str = "") -> dict[str, Any]:
    """Return the ``mcpServers["graphify"]`` entry for the local HTTP MCP server."""
    entry: dict[str, Any] = {
        "type": "http",
        "url": f"http://127.0.0.1:{port}/mcp",
    }
    if api_key:
        entry["headers"] = {"Authorization": f"Bearer {api_key}"}
    return entry


def register_graphify_claude_server(port: int, api_key: str = "") -> dict[str, Any]:
    """Write the ``graphify`` sibling entry into ``~/.claude.json`` mcpServers.

    Preserves any existing ``graphify._comment`` and every other top-level key /
    server entry. Idempotent: re-writing with a new port refreshes the URL.
    """
    path = claude_json_path()
    data = _load_claude_json()
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers

    entry = build_graphify_server_entry(port, api_key)
    existing = servers.get(GRAPHIFY_SERVER_NAME)
    if isinstance(existing, dict) and "_comment" in existing:
        entry["_comment"] = existing["_comment"]
    else:
        entry["_comment"] = (
            "Local Graphify knowledge-graph MCP server. Managed by fcc-server's "
            "Graphify admin view; start/stop rewrites this entry. Sibling of "
            "'mcp-router', not a backend inside it."
        )

    servers[GRAPHIFY_SERVER_NAME] = entry
    _atomic_write(path, data)
    logger.info(
        "GRAPHIFY_CLAUDE_MCP: registered sibling 'graphify' server at port {}", port
    )
    return {"registered": True, "port": port, "path": str(path)}


def unregister_graphify_claude_server() -> dict[str, Any]:
    """Remove the ``graphify`` sibling entry from ``~/.claude.json`` mcpServers."""
    path = claude_json_path()
    if not path.exists():
        return {"registered": False, "path": str(path)}
    data = _load_claude_json()
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or GRAPHIFY_SERVER_NAME not in servers:
        return {"registered": False, "path": str(path)}
    del servers[GRAPHIFY_SERVER_NAME]
    _atomic_write(path, data)
    logger.info("GRAPHIFY_CLAUDE_MCP: unregistered sibling 'graphify' server")
    return {"registered": False, "path": str(path)}


def graphify_claude_server_registered() -> bool:
    """Return True when a ``graphify`` entry currently exists in ~/.claude.json."""
    servers = _load_claude_json().get("mcpServers")
    return isinstance(servers, dict) and GRAPHIFY_SERVER_NAME in servers
