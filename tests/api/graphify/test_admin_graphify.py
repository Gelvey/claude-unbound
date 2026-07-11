"""Tests for Graphify admin routes."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


def _local_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def client(graphify_tmp_home: Path, monkeypatch) -> TestClient:
    """Provide a TestClient with Graphify enabled in cached settings."""
    monkeypatch.setenv("GRAPHIFY_ENABLED", "true")
    monkeypatch.setenv("GRAPHIFY_API_KEY", "secret")
    app = create_app(lifespan_enabled=False)
    return _local_client(app)


@pytest.fixture
def _mock_running_manager(client: TestClient):
    """Attach a mock GraphifyManager that appears running."""
    manager = MagicMock()
    manager.is_running = True
    manager.port = 9876
    manager.last_error = None
    manager.status = MagicMock(
        return_value={
            "enabled": True,
            "running": True,
            "port": 9876,
            "python": "/fake/python",
            "last_error": None,
            "projects_count": 0,
            "projects_summary": [],
        }
    )
    manager.health_check = AsyncMock(return_value={"status": "healthy"})
    client.app.state.graphify_manager = manager
    return manager


def test_status_requires_loopback(graphify_tmp_home: Path, monkeypatch) -> None:
    monkeypatch.setenv("GRAPHIFY_ENABLED", "true")
    app = create_app(lifespan_enabled=False)
    remote = TestClient(app, client=("203.0.113.10", 50000))

    assert remote.get("/admin/api/graphify/status").status_code == 403


def test_status_returns_manager_state(
    client: TestClient,
    _mock_running_manager: Any,
) -> None:
    response = client.get("/admin/api/graphify/status")

    assert response.status_code == 200
    data = response.json()
    assert data["running"] is True
    assert data["port"] == 9876


def test_setup_runs_manager_setup(
    client: TestClient,
) -> None:
    manager = AsyncMock()
    manager.setup.return_value = {"ready": True, "python": "/fake/python"}
    client.app.state.graphify_manager = manager

    response = client.post("/admin/api/graphify/setup")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    manager.setup.assert_awaited_once()


def test_projects_crud(
    client: TestClient,
    graphify_tmp_home: Path,
) -> None:
    project_path = str(graphify_tmp_home / "repo")
    Path(project_path).mkdir()

    add_response = client.post(
        "/admin/api/graphify/projects",
        json={"path": project_path, "name": "Repo"},
    )
    assert add_response.status_code == 200
    assert add_response.json()["success"] is True

    list_response = client.get("/admin/api/graphify/projects")
    assert list_response.status_code == 200
    projects = list_response.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["name"] == "Repo"

    path_b64 = (
        base64.urlsafe_b64encode(project_path.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    delete_response = client.delete(f"/admin/api/graphify/projects/{path_b64}")
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    list_response = client.get("/admin/api/graphify/projects")
    assert list_response.json()["projects"] == []


@pytest.mark.asyncio
async def test_index_project_routes_to_manager(
    client: TestClient,
    graphify_tmp_home: Path,
) -> None:
    project_path = str(graphify_tmp_home / "repo")
    Path(project_path).mkdir()

    client.post(
        "/admin/api/graphify/projects",
        json={"path": project_path, "name": "Repo"},
    )

    manager = AsyncMock()
    manager.start_index_project.return_value = {
        "success": True,
        "status": "started",
        "path": project_path,
    }
    client.app.state.graphify_manager = manager

    path_b64 = (
        base64.urlsafe_b64encode(project_path.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    response = client.post(f"/admin/api/graphify/projects/{path_b64}/index")

    assert response.status_code == 200
    assert response.json()["success"] is True
    manager.start_index_project.assert_awaited_once()


def test_graph_summary_route_returns_counts(
    client: TestClient,
    graphify_tmp_home: Path,
) -> None:
    import json

    project_path = str(graphify_tmp_home / "repo")
    Path(project_path).mkdir()
    (Path(project_path) / "graphify-out").mkdir(parents=True)
    (Path(project_path) / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "a", "file_type": "code", "community": 1},
                    {"id": "b", "file_type": "docs"},
                ],
                "links": [{"source": "a", "target": "b"}],
                "hyperedges": [],
                "built_at_commit": "abc1234",
            }
        )
    )
    client.post(
        "/admin/api/graphify/projects", json={"path": project_path, "name": "Repo"}
    )
    path_b64 = (
        base64.urlsafe_b64encode(project_path.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    response = client.get(f"/admin/api/graphify/projects/{path_b64}/graph")

    assert response.status_code == 200
    data = response.json()
    assert data["present"] is True
    assert data["node_count"] == 2
    assert data["link_count"] == 1
    assert data["built_at_commit"] == "abc1234"


def test_graph_summary_route_not_indexed(
    client: TestClient, graphify_tmp_home: Path
) -> None:
    project_path = str(graphify_tmp_home / "repo")
    Path(project_path).mkdir()
    client.post(
        "/admin/api/graphify/projects", json={"path": project_path, "name": "Repo"}
    )
    path_b64 = (
        base64.urlsafe_b64encode(project_path.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    response = client.get(f"/admin/api/graphify/projects/{path_b64}/graph")

    assert response.status_code == 200
    assert response.json()["present"] is False


def test_graph_summary_route_404_for_unknown_project(client: TestClient) -> None:
    path_b64 = base64.urlsafe_b64encode(b"/no/such/repo").decode("ascii").rstrip("=")
    response = client.get(f"/admin/api/graphify/projects/{path_b64}/graph")
    assert response.status_code == 404
