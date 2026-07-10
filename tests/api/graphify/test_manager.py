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


def _mcp_ok_response() -> Any:
    """A mocked Streamable HTTP initialize response (200 + SSE-framed JSON)."""
    return MagicMock(
        status_code=200,
        text=(
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",'
            '"capabilities":{},"serverInfo":{"name":"graphify","version":"1.28.1"}}}'
        ),
    )


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
            "api.graphify.manager.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=_mcp_ok_response(),
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
async def test_manager_start_does_not_register_backend_when_not_ready(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """Reorder guarantee: the MCP backend is not published until the server is ready."""
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
            "api.graphify.manager.GraphifyManager._wait_for_ready",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("api.graphify.manager.add_graphify_mcp_backend") as add_backend,
        patch(
            "api.graphify.manager.reload_mcp_router_async",
            new_callable=AsyncMock,
            return_value={"reloaded": True},
        ),
    ):
        started = await manager.start()

    assert started is False
    assert manager.last_error == "Graphify health check timed out"
    add_backend.assert_not_called()


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
            "api.graphify.manager.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=_mcp_ok_response(),
        ),
    ):
        await manager.start()
        health = await manager.health_check()

    assert health["status"] == "healthy"
    assert health["http_status"] == 200
    assert health["server_info"]["name"] == "graphify"


@pytest.mark.asyncio
async def test_manager_health_check_reports_unhealthy_on_non_200(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_python_path="/fake/python")
    manager._base_url = "http://127.0.0.1:9876"

    with patch(
        "api.graphify.manager.httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=406,
            text='data: {"jsonrpc":"2.0","error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}',
        ),
    ):
        health = await manager.health_check()

    assert health["status"] == "unhealthy"
    assert health["http_status"] == 406
    assert "Not Acceptable" in health["error"]


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


# ---------------------------------------------------------------------------
# Probe / env helpers
# ---------------------------------------------------------------------------


def test_parse_sse_data_extracts_json_payload() -> None:
    from api.graphify.manager import _parse_sse_data

    text = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"graphify"}}}\n'
    )
    data = _parse_sse_data(text)
    assert isinstance(data, dict)
    assert data["result"]["serverInfo"]["name"] == "graphify"


def test_parse_sse_data_returns_none_when_no_data_line() -> None:
    from api.graphify.manager import _parse_sse_data

    assert _parse_sse_data("") is None
    assert _parse_sse_data("event: message\n") is None


def test_parse_sse_data_skips_malformed_data_lines() -> None:
    from api.graphify.manager import _parse_sse_data

    text = 'data: not-json\ndata: {"ok": true}\n'
    data = _parse_sse_data(text)
    assert data == {"ok": True}


def test_extract_jsonrpc_error_returns_message() -> None:
    from api.graphify.manager import _extract_jsonrpc_error

    assert _extract_jsonrpc_error({"error": {"message": "boom"}}) == "boom"


def test_extract_jsonrpc_error_returns_none_without_error() -> None:
    from api.graphify.manager import _extract_jsonrpc_error

    assert _extract_jsonrpc_error({"result": {}}) is None
    assert _extract_jsonrpc_error(None) is None


def test_manager_probe_headers_include_auth_when_key_set(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_api_key="tok")
    headers = manager._mcp_probe_headers()
    assert headers["Accept"] == "application/json, text/event-stream"
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"] == "Bearer tok"


def test_manager_probe_headers_omit_auth_when_no_key(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_api_key="")
    headers = manager._mcp_probe_headers()
    assert "Authorization" not in headers


def test_manager_extract_env_injects_llm_key(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "preexisting")
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="ollama",
        graphify_llm_api_key="dummy",
    )
    env = manager._extract_env()
    assert env["OPENAI_API_KEY"] == "preexisting"
    assert env["OLLAMA_API_KEY"] == "dummy"


def test_manager_extract_env_without_llm_backend_inherits_only(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    manager = _build_manager(graphify_settings)
    env = manager._extract_env()
    assert "OLLAMA_API_KEY" not in env


def test_manager_extract_env_ignores_unknown_backend(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="nope",
        graphify_llm_api_key="dummy",
    )
    env = manager._extract_env()
    assert "ANTHROPIC_API_KEY" not in env
