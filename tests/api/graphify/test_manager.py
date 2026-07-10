"""Tests for GraphifyManager lifecycle and project indexing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.graphify.config import GraphifyProject, GraphifyProjectRegistry
from api.graphify.manager import GraphifyManager
from api.graphify.projects import load_project_registry
from api.mcp_config import load_mcp_config


def _async_process_mock(returncode: int | None = None) -> Any:
    process = MagicMock()
    process.returncode = returncode
    process.pid = 12345
    process.wait = AsyncMock(return_value=None)
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.send_signal = MagicMock()
    return process


def _build_manager(graphify_settings: Any, **overrides: Any) -> GraphifyManager:
    from config.settings import Settings

    fields = {**graphify_settings.model_dump(), **overrides}
    return GraphifyManager(Settings.model_construct(**fields))


def _register_project(path: Path, name: str = "repo") -> GraphifyProject:
    from api.graphify.projects import add_or_update_project, save_project_registry

    registry = GraphifyProjectRegistry()
    add_or_update_project(registry, path=str(path), name=name)
    save_project_registry(registry)
    return registry.projects[0]


@pytest.mark.asyncio
async def test_manager_setup_succeeds_with_importable_python(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_python_path="/fake/python")

    with patch("api.graphify.manager._is_graphify_importable", return_value=True):
        result = await manager.setup(create_venv=True)

    assert result["ready"] is True
    assert result["python"] == "/fake/python"
    assert result["method"] == "venv"


@pytest.mark.asyncio
async def test_manager_start_stops_writes_and_removes_backend(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_python_path="/fake/python")
    process = _async_process_mock(returncode=None)

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch("api.graphify.manager._find_free_port", return_value=9876),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ) as create_subprocess,
        patch(
            "api.graphify.manager.reload_mcp_router_async",
            new_callable=AsyncMock,
            return_value={"reloaded": False, "error": "test fallback"},
        ) as reload_router,
        patch(
            "api.graphify.manager.restart_mcp_router_async",
            new_callable=AsyncMock,
            return_value={"restarted": True},
        ) as restart_router,
        patch(
            "api.graphify.manager.httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=MagicMock(status_code=200, json=MagicMock(return_value={})),
        ),
    ):
        started = await manager.start()

        assert started is True
        assert manager.is_running
        assert manager.port == 9876
        create_subprocess.assert_called_once()
        assert create_subprocess.call_args.args[:5] == (
            "/fake/python",
            "-m",
            "graphify.serve",
            "--transport",
            "http",
        )

        config, _ = load_mcp_config()
        assert "graphify" in config.servers
        assert config.servers["graphify"].url == "http://127.0.0.1:9876/mcp"
        reload_router.assert_awaited()

        await manager.stop()

        assert not manager.is_running
        config, _ = load_mcp_config()
        assert "graphify" not in config.servers
        restart_router.assert_awaited()


@pytest.mark.asyncio
async def test_manager_health_checks_running_server(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_python_path="/fake/python")
    process = _async_process_mock(returncode=None)

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch("api.graphify.manager._find_free_port", return_value=9876),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ),
        patch(
            "api.graphify.manager.reload_mcp_router_async",
            new_callable=AsyncMock,
            return_value={"reloaded": True, "summary": {}},
        ),
        patch(
            "api.graphify.manager.httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=MagicMock(
                status_code=200, json=MagicMock(return_value={"ok": True})
            ),
        ),
    ):
        await manager.start()
        health = await manager.health_check()

    assert health["status"] == "healthy"
    assert health["http_status"] == 200


@pytest.mark.asyncio
async def test_manager_status_includes_projects_summary(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings)

    status = manager.status()
    assert status["enabled"] is True

    _register_project(graphify_tmp_home / "project", name="project")

    status = manager.status()
    assert status["projects_count"] == 1
    assert status["projects_summary"][0]["name"] == "project"


@pytest.mark.asyncio
async def test_manager_index_project_runs_extract(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    project = _register_project(repo_path)
    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
    )
    success_process = _async_process_mock(returncode=0)
    success_process.communicate = AsyncMock(return_value=(b"extracted", b""))

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=success_process,
        ),
    ):
        result = await manager.index_project(project)

    assert result["success"] is True
    assert result["mode"] == "extract"
    assert success_process.communicate.awaited


@pytest.mark.asyncio
async def test_manager_index_project_reports_failure(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    project = _register_project(repo_path)
    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
    )
    fail_process = _async_process_mock(returncode=1)
    fail_process.communicate = AsyncMock(return_value=(b"", b"graphify failed"))

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=fail_process,
        ),
    ):
        result = await manager.index_project(project)

    assert result["success"] is False
    assert "graphify failed" in result["error"]


@pytest.mark.asyncio
async def test_manager_index_project_enforces_max_project_bytes(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    (repo_path / "large.bin").write_bytes(b"x" * 2048)
    project = _register_project(repo_path)

    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
        graphify_max_project_bytes=1024,
    )

    with patch("api.graphify.manager._is_graphify_importable", return_value=True):
        result = await manager.index_project(project)

    assert result["success"] is False
    assert "exceeds" in result["error"]


@pytest.mark.asyncio
async def test_manager_start_index_project_runs_in_background(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    project = _register_project(repo_path)

    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
    )
    success_process = _async_process_mock(returncode=0)
    success_process.communicate = AsyncMock(return_value=(b"extracted", b""))

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=success_process,
        ),
    ):
        start_result = await manager.start_index_project(project)
        assert start_result["success"] is True
        assert start_result["status"] == "started"

        # The task status should be visible immediately
        task_status = manager.get_index_task_status(project.path)
        assert task_status is not None
        assert task_status["status"] == "indexing"

        # Wait for the background task to complete; the task entry is removed
        # once it finishes, so also poll the persisted project status.
        for _ in range(200):
            await asyncio.sleep(0.01)
            if not manager._indexing_tasks:
                break

        assert not manager._indexing_tasks
        status = load_project_registry().projects[0]
        assert status.status == "ready"
        assert status.last_indexed is not None


@pytest.mark.asyncio
async def test_manager_start_index_project_returns_already_running(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    project = _register_project(repo_path)

    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
    )
    slow_process = _async_process_mock(returncode=None)

    async def _slow_communicate():
        await asyncio.sleep(0.3)
        return (b"", b"")

    slow_process.communicate = AsyncMock(side_effect=_slow_communicate)

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=slow_process,
        ),
    ):
        first = await manager.start_index_project(project)
        assert first["status"] == "started"
        second = await manager.start_index_project(project)
        assert second["status"] == "already_running"
