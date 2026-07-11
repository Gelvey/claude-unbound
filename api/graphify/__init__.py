"""Graphify MCP integration for Claude Unbound."""

from __future__ import annotations

from api.graphify.claude_mcp import (
    register_graphify_claude_server,
    unregister_graphify_claude_server,
)
from api.graphify.config import GraphifyProject, GraphifyProjectRegistry
from api.graphify.manager import GraphifyManager
from api.graphify.projects import (
    add_or_update_project,
    load_project_registry,
    remove_project,
    save_project_registry,
)

__all__ = [
    "GraphifyManager",
    "GraphifyProject",
    "GraphifyProjectRegistry",
    "add_or_update_project",
    "load_project_registry",
    "register_graphify_claude_server",
    "remove_project",
    "save_project_registry",
    "unregister_graphify_claude_server",
]
