"""Read summary stats from a Graphify project's ``graph.json``.

The full graph can be many megabytes, so only a compact summary is computed
and returned to the admin panel — never the raw graph.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from .config import GraphifyProject


def graph_json_path(project: GraphifyProject) -> Path:
    """Return the path to a project's ``graphify-out/graph.json``."""
    return Path(project.path) / project.graphify_out / "graph.json"


def read_graph_summary(project: GraphifyProject) -> dict[str, Any]:
    """Return a compact summary of a project's knowledge graph.

    ``{"present": False, "reason": ...}`` when the graph has not been built yet
    or is unreadable; never raises.
    """
    path = graph_json_path(project)
    if not path.exists():
        return {"present": False, "reason": "not_indexed"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("GRAPHIFY_GRAPHS: unreadable graph {}: {}", path, exc)
        return {"present": False, "reason": "unreadable", "error": str(exc)}

    nodes = data.get("nodes") or []
    links = data.get("links") or []
    hyperedges = data.get("hyperedges") or []
    file_types: Counter[str] = Counter()
    communities: set[Any] = set()
    for node in nodes:
        if isinstance(node, dict):
            ft = node.get("file_type")
            if isinstance(ft, str) and ft:
                file_types[ft] += 1
            community = node.get("community")
            if community is not None:
                communities.add(community)
    return {
        "present": True,
        "built_at_commit": data.get("built_at_commit"),
        "node_count": len(nodes),
        "link_count": len(links),
        "hyperedge_count": len(hyperedges),
        "file_types": dict(file_types),
        "communities": len(communities),
    }
