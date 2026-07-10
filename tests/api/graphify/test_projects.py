"""Tests for the Graphify project registry helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.graphify.config import GraphifyProjectRegistry
from api.graphify.projects import (
    add_or_update_project,
    load_project_registry,
    remove_project,
    save_project_registry,
    update_project_status,
)


@pytest.fixture
def registry() -> GraphifyProjectRegistry:
    """Return an empty registry."""
    return GraphifyProjectRegistry()


def test_load_missing_registry_returns_empty(graphify_tmp_home: Path) -> None:
    registry = load_project_registry()
    assert registry.projects == []
    assert registry.active_project_path is None


def test_add_project_creates_entry(registry: GraphifyProjectRegistry) -> None:
    path = "/tmp/graphify-test-repo"
    project = add_or_update_project(registry, path, name="My Repo")

    assert project.path == str(Path(path).resolve())
    assert project.name == "My Repo"
    assert project.status == "missing"


def test_add_project_uses_directory_name_by_default(
    registry: GraphifyProjectRegistry,
) -> None:
    project = add_or_update_project(registry, "/home/user/src/my-app")
    assert project.name == "my-app"


def test_update_existing_project_preserves_path(
    registry: GraphifyProjectRegistry,
) -> None:
    path = "/tmp/graphify-test-repo"
    add_or_update_project(registry, path, name="Old")
    updated = add_or_update_project(registry, path, name="New")

    assert len(registry.projects) == 1
    assert updated.name == "New"
    assert registry.projects[0].name == "New"


def test_remove_unknown_project_returns_false(
    registry: GraphifyProjectRegistry,
) -> None:
    assert remove_project(registry, "/no/such/path") is False
    assert registry.projects == []


def test_remove_project_clears_active(registry: GraphifyProjectRegistry) -> None:
    path = "/tmp/graphify-test-repo"
    project = add_or_update_project(registry, path)
    registry.active_project_path = project.path

    assert remove_project(registry, path) is True
    assert registry.active_project_path is None
    assert registry.projects == []


def test_save_and_load_registry_roundtrip(
    registry: GraphifyProjectRegistry,
    graphify_tmp_home: Path,
) -> None:
    add_or_update_project(registry, "/tmp/graphify-test-repo", name="App")
    save_project_registry(registry)

    loaded = load_project_registry()
    assert len(loaded.projects) == 1
    assert loaded.projects[0].name == "App"
    assert loaded.projects[0].path == str(Path("/tmp/graphify-test-repo").resolve())


def test_update_project_status(registry: GraphifyProjectRegistry) -> None:
    add_or_update_project(registry, "/tmp/graphify-test-repo")
    update_project_status(registry, "/tmp/graphify-test-repo", status="indexing")

    assert registry.projects[0].status == "indexing"


def test_load_corrupt_registry_raises(graphify_tmp_home: Path) -> None:
    from api.graphify.paths import projects_json_path

    projects_json_path().parent.mkdir(parents=True, exist_ok=True)
    projects_json_path().write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_project_registry()
