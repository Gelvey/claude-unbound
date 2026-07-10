"""Tests for Graphify MCP tool metadata used by the project-routing directive.

``GRAPHIFY_TOOL_NAMES`` drives the system directive that tells the model which
tools must carry a ``project_path`` argument. It must match the tools
``graphify.serve`` actually exposes (see ``graphify/serve.py`` list_tools), or
the model will be told to route tools that don't exist and miss real ones.
"""

from __future__ import annotations

from api.graphify.mcp_proxy import GRAPHIFY_TOOL_NAMES


def test_graphify_tool_names_match_real_server_tools() -> None:
    expected = frozenset(
        {
            "query_graph",
            "get_node",
            "get_neighbors",
            "get_community",
            "god_nodes",
            "graph_stats",
            "shortest_path",
            "list_prs",
            "get_pr_impact",
            "triage_prs",
        }
    )
    assert expected == GRAPHIFY_TOOL_NAMES


def test_graphify_tool_names_exclude_nonexistent_affected() -> None:
    """``affected`` is a graphify CLI command, not an exposed MCP tool."""
    assert "affected" not in GRAPHIFY_TOOL_NAMES


def test_graphify_tool_names_cover_neighbor_and_pr_tools() -> None:
    """Regression guards for tools the old set was missing."""
    assert "get_neighbors" in GRAPHIFY_TOOL_NAMES
    assert "get_community" in GRAPHIFY_TOOL_NAMES
    assert "list_prs" in GRAPHIFY_TOOL_NAMES
    assert "get_pr_impact" in GRAPHIFY_TOOL_NAMES
    assert "triage_prs" in GRAPHIFY_TOOL_NAMES
