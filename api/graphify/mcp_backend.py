"""MCP backend entry builders for Graphify."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from api.mcp_config import McpBackend, load_mcp_config, write_mcp_config


def build_graphify_mcp_backend(port: int, api_key: str = "") -> dict[str, Any]:
    """Return an ``McpBackend`` dict for the local Graphify HTTP server."""
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return {
        "name": "graphify",
        "type": "http",
        "port": port,
        "url": f"http://127.0.0.1:{port}/mcp",
        "headers": headers,
    }


def add_graphify_mcp_backend(
    port: int,
    api_key: str = "",
) -> dict[str, Any]:
    """Register the graphify backend in ``mcp_config.json`` and return result data."""
    backend = build_graphify_mcp_backend(port, api_key)
    return _persist_backend(backend)


def remove_graphify_mcp_backend() -> dict[str, Any]:
    """Remove the graphify backend from ``mcp_config.json`` and return result data."""
    return _persist_backend(None)


def _persist_backend(backend: dict[str, Any] | None) -> dict[str, Any]:
    config, _path = load_mcp_config()
    if backend is not None:
        name = backend["name"]
        config.servers[name] = McpBackend(**backend)
    elif "graphify" in config.servers:
        del config.servers["graphify"]

    result = write_mcp_config(
        router_socket=config.router_socket,
        router_log=config.router_log,
        router_pidfile=config.router_pidfile,
        health_timeout_s=config.health_timeout_s,
        servers={
            name: srv.model_dump(exclude={"name"})
            for name, srv in config.servers.items()
        },
        shared_servers={
            name: srv.model_dump(exclude={"name"})
            for name, srv in config.shared_servers.items()
        },
    )
    data = result.model_dump()
    if backend is not None and result.valid and result.applied:
        data["backend"] = {k: v for k, v in backend.items() if k != "name"}
    return data


def merge_graphify_backend(
    servers: dict[str, dict[str, Any]],
    modules: Iterable[Any],
) -> dict[str, dict[str, Any]]:
    """Re-add a graphify backend when the user edits MCP config in the admin UI.

    This is intentionally a no-op helper; graphify is managed by
    :class:`~api.graphify.manager.GraphifyManager`, not by hand-edited MCP
    config.
    """
    return dict(servers)
