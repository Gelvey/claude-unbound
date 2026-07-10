"""Graphify MCP tool metadata for per-session project routing.

Claude Unbound tags each Claude Code session with a repo path via the
``ANTHROPIC_AUTH_TOKEN`` suffix (``:graphify-repo:<base64>``). Because the MCP
meta-router is a single shared Unix-socket process with no per-connection
context, the repo path cannot be injected at the wire level. Instead
``api/request_pipeline.py`` appends a system directive naming these tools and
the resolved ``project_path`` so the model includes ``project_path`` in its
Graphify tool calls; graphify's server routes each call to
``<project_path>/graphify-out/graph.json`` (see ``graphify/serve.py``:
"Multi-project support: every tool accepts an optional project_path").

``GRAPHIFY_TOOL_NAMES`` is the canonical list of tools the directive covers and
must stay in lockstep with the tools graphify's server actually exposes.
"""

from __future__ import annotations

GRAPHIFY_TOOL_NAMES: frozenset[str] = frozenset(
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
