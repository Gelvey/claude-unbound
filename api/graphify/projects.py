"""Graphify project registry persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.graphify.config import GraphifyProject, GraphifyProjectRegistry
from api.graphify.paths import projects_json_path


class _ProjectNotFoundError(KeyError):
    pass


def load_project_registry(path: Path | None = None) -> GraphifyProjectRegistry:
    """Load the project registry from disk, returning an empty one if absent."""
    target = path or projects_json_path()
    if not target.exists():
        return GraphifyProjectRegistry()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"Could not read Graphify registry at {target}: {exc}"
        ) from exc
    return GraphifyProjectRegistry.model_validate(data)


def save_project_registry(
    registry: GraphifyProjectRegistry, path: Path | None = None
) -> None:
    """Persist the project registry atomically."""
    target = path or projects_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        registry.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)


def _normalize_project_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _find_project_index(registry: GraphifyProjectRegistry, path: str) -> int:
    normalized = _normalize_project_path(path)
    for index, project in enumerate(registry.projects):
        if _normalize_project_path(project.path) == normalized:
            return index
    raise _ProjectNotFoundError(f"No registered project at {path}")


def add_or_update_project(
    registry: GraphifyProjectRegistry,
    path: str,
    name: str | None = None,
    graphify_out: str = "graphify-out",
) -> GraphifyProject:
    """Add a new project or update an existing one by resolved path."""
    normalized = _normalize_project_path(path)
    try:
        index = _find_project_index(registry, normalized)
    except _ProjectNotFoundError:
        project = GraphifyProject(
            path=normalized,
            name=name or Path(normalized).name,
            graphify_out=graphify_out,
        )
        registry.projects.append(project)
        return project

    project = registry.projects[index]
    if name is not None:
        project.name = name
    if graphify_out:
        project.graphify_out = graphify_out
    return project


def remove_project(registry: GraphifyProjectRegistry, path: str) -> bool:
    """Remove a project by resolved path. Returns True if removed."""
    try:
        index = _find_project_index(registry, path)
    except _ProjectNotFoundError:
        return False
    registry.projects.pop(index)
    if _normalize_project_path(path) == registry.active_project_path:
        registry.active_project_path = None
    return True


def update_project_status(
    registry: GraphifyProjectRegistry,
    path: str,
    *,
    status: Any,
    error_message: str = "",
) -> GraphifyProject:
    """Update the indexing status of a registered project."""
    project = registry.projects[_find_project_index(registry, path)]
    project.status = status
    project.error_message = error_message
    return project
