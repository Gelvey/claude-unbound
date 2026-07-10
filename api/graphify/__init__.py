"""Graphify MCP integration for Claude Unbound."""

from __future__ import annotations

from api.graphify.config import GraphifyProject, GraphifyProjectRegistry
from api.graphify.manager import GraphifyManager
from api.graphify.mcp_backend import build_graphify_mcp_backend
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
    "build_graphify_mcp_backend",
    "load_project_registry",
    "remove_project",
    "save_project_registry",
]
