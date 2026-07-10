"""Graphify MCP tool-call injection helpers.

Claude Unbound tags each Claude Code session with a repo path via the
``ANTHROPIC_AUTH_TOKEN`` suffix.  This module provides the helper that
injects the decoded ``project_path`` argument into Graphify MCP tool calls
so the Graphify server can route them to the correct project graph.
"""

from __future__ import annotations

from typing import Any

GRAPHIFY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "query_graph",
        "get_node",
        "god_nodes",
        "shortest_path",
        "affected",
        "graph_stats",
    }
)


_GRAPHIFY_PROJECT_PATH_ARG = "project_path"


def inject_project_path(
    arguments: dict[str, Any],
    project_path: str | None,
    *,
    tool_name: str | None = None,
) -> dict[str, Any]:
    """Return a copy of *arguments* with ``project_path`` injected when known.

    The injection is performed for Graphify tools and only when a non-empty
    *project_path* is provided.  Existing ``project_path`` values already set
    by the client are preserved to allow explicit overrides.
    """
    if not project_path:
        return arguments
    if tool_name is not None and tool_name not in GRAPHIFY_TOOL_NAMES:
        return arguments
    if _GRAPHIFY_PROJECT_PATH_ARG in arguments:
        return arguments
    updated = dict(arguments)
    updated[_GRAPHIFY_PROJECT_PATH_ARG] = project_path
    return updated


def is_graphify_tool(tool_name: str) -> bool:
    """Return whether *tool_name* is a Graphify tool handled by this proxy."""
    base = tool_name
    if "__" in tool_name:
        base = tool_name.split("__", 1)[1]
    return base in GRAPHIFY_TOOL_NAMES
