"""Tests for GraphifyManager lifecycle and project indexing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.graphify.claude_mcp import GRAPHIFY_SERVER_NAME, claude_json_path
from api.graphify.config import GraphifyProject, GraphifyProjectRegistry
from api.graphify.manager import GraphifyManager
from api.graphify.projects import load_project_registry


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
async def test_manager_start_stop_registers_and_unregisters_claude_server(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """Start writes the graphify sibling entry to ~/.claude.json; stop removes it."""
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
        # GRAPHIFY_STATELESS defaults to True, so --stateless must be in argv.
        argv = create_subprocess.call_args.args
        assert argv[:5] == (
            "/fake/python",
            "-m",
            "graphify.serve",
            "--transport",
            "http",
        )
        assert "--host" in argv
        assert "127.0.0.1" in argv
        assert "--port" in argv
        assert "9876" in argv
        assert "--stateless" in argv

        data = json.loads(claude_json_path().read_text())
        servers = data["mcpServers"]
        assert GRAPHIFY_SERVER_NAME in servers
        assert servers[GRAPHIFY_SERVER_NAME]["url"] == "http://127.0.0.1:9876/mcp"
        assert servers[GRAPHIFY_SERVER_NAME]["headers"] == {
            "Authorization": "Bearer secret-key"
        }
        assert manager.status()["mcp_registered"] is True

        await manager.stop()

        assert not manager.is_running
        data = json.loads(claude_json_path().read_text())
        assert GRAPHIFY_SERVER_NAME not in data.get("mcpServers", {})
        assert manager.status()["mcp_registered"] is False


@pytest.mark.asyncio
async def test_manager_start_passes_stateless_flag_by_default(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """Default GRAPHIFY_STATELESS=true appends --stateless to graphify.serve argv.

    Without --stateless, the upstream graphifyy StreamableHTTPSessionManager
    requires an mcp-session-id header on every tools/call POST and rejects
    requests without it as 'Missing session ID' (HTTP 400). Claude Code's MCP
    SDK maps that to a generic 'Unable to connect' tool failure, so the
    server must run in stateless mode by default to remain usable.
    """
    manager = _build_manager(graphify_settings, graphify_python_path="/fake/python")
    process = _async_process_mock(returncode=None)
    captured: dict[str, tuple[str, ...]] = {}

    def _capture(*args: object, **kwargs: object) -> AsyncMock:
        # Strip kwargs (env=...) and capture the positional argv.
        argv = tuple(arg for arg in args if isinstance(arg, str))
        captured["argv"] = argv
        return process

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch("api.graphify.manager._find_free_port", return_value=9876),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_capture),
        ),
        patch(
            "api.graphify.manager.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=_mcp_ok_response(),
        ),
    ):
        await manager.start()

    assert "--stateless" in captured["argv"]
    await manager.stop()


@pytest.mark.asyncio
async def test_manager_start_omits_stateless_flag_when_disabled(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """Set GRAPHIFY_STATELESS=false to keep the legacy stateful session flow."""
    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
        graphify_stateless=False,
    )
    process = _async_process_mock(returncode=None)
    captured: dict[str, tuple[str, ...]] = {}

    def _capture(*args: object, **kwargs: object) -> AsyncMock:
        argv = tuple(arg for arg in args if isinstance(arg, str))
        captured["argv"] = argv
        return process

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch("api.graphify.manager._find_free_port", return_value=9876),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=_capture),
        ),
        patch(
            "api.graphify.manager.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=_mcp_ok_response(),
        ),
    ):
        await manager.start()

    assert "--stateless" not in captured["argv"]
    await manager.stop()


@pytest.mark.asyncio
async def test_manager_start_does_not_register_when_not_ready(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """Reorder guarantee: the Claude Code MCP entry is not written until the server is ready."""
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
        patch(
            "api.graphify.manager.register_graphify_claude_server"
        ) as register_server,
    ):
        started = await manager.start()

    assert started is False
    assert manager.last_error == "Graphify health check timed out"
    register_server.assert_not_called()


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


# ---------------------------------------------------------------------------
# Cloudflare / OpenAI-compatible extraction backend
# ---------------------------------------------------------------------------


def test_manager_extract_env_cloudflare_redirects_openai_backend(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cloudflare rides graphify's openai backend pointed at the CF endpoint."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_api_key="cf-key",
        cloudflare_ai_account_id="acct123",
        graphify_llm_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    )
    env = manager._extract_env()
    assert env["OPENAI_API_KEY"] == "cf-key"
    assert (
        env["OPENAI_BASE_URL"]
        == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
    )
    assert env["GRAPHIFY_OPENAI_MODEL"] == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def test_manager_extract_env_cloudflare_reuses_provider_key(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blank GRAPHIFY_LLM_API_KEY falls back to the Cloudflare provider key."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_api_key="",
        cloudflare_ai_api_key="cf-provider-key",
        cloudflare_ai_account_id="acct456",
    )
    env = manager._extract_env()
    assert env["OPENAI_API_KEY"] == "cf-provider-key"
    assert "accounts/acct456/ai/v1" in env["OPENAI_BASE_URL"]
    assert "GRAPHIFY_OPENAI_MODEL" not in env


def test_manager_extract_env_cloudflare_honours_base_url_override(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        cloudflare_ai_api_key="k",
        cloudflare_ai_base_url="https://gateway.example.com/ai/v1",
    )
    env = manager._extract_env()
    assert env["OPENAI_BASE_URL"] == "https://gateway.example.com/ai/v1"


# ---------------------------------------------------------------------------
# LM Studio extraction backend (OpenAI-compatible via lm_studio_base_url)
# ---------------------------------------------------------------------------


def test_manager_extract_env_lmstudio_redirects_openai_backend(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lmstudio rides graphify's openai backend pointed at the LM Studio endpoint."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="lmstudio",
        graphify_llm_api_key="",
        lm_studio_base_url="http://localhost:1234/v1",
        graphify_llm_model="qwen2.5-coder-7b-instruct",
    )
    env = manager._extract_env()
    assert env["OPENAI_API_KEY"] == "lm-studio"
    assert env["OPENAI_BASE_URL"] == "http://localhost:1234/v1"
    assert env["GRAPHIFY_OPENAI_MODEL"] == "qwen2.5-coder-7b-instruct"


def test_manager_extract_env_lmstudio_uses_provided_api_key(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit GRAPHIFY_LLM_API_KEY is forwarded as OPENAI_API_KEY."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="lmstudio",
        graphify_llm_api_key="real-key",
        lm_studio_base_url="http://localhost:1234/v1",
    )
    env = manager._extract_env()
    assert env["OPENAI_API_KEY"] == "real-key"


def test_manager_extract_env_lmstudio_omits_model_when_blank(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GRAPHIFY_OPENAI_MODEL is only set when GRAPHIFY_LLM_MODEL is non-empty."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="lmstudio",
        graphify_llm_api_key="",
        lm_studio_base_url="http://localhost:1234/v1",
        graphify_llm_model="",
    )
    env = manager._extract_env()
    assert "GRAPHIFY_OPENAI_MODEL" not in env


def test_build_extract_args_lmstudio_passes_openai_backend(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """lmstudio maps to --backend openai on the graphify CLI."""
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="lmstudio",
        graphify_llm_model="qwen2.5-coder-7b-instruct",
    )
    project = _register_project(graphify_tmp_home)
    args = manager._build_extract_args(project, "extract")
    assert "--backend" in args
    assert args[args.index("--backend") + 1] == "openai"


# ---------------------------------------------------------------------------
# FCC provider-prefix stripping
# ---------------------------------------------------------------------------


def test_manager_extract_env_cloudflare_strips_fcc_prefix(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FCC-format model id 'cloudflare_ai/@cf/moonshotai/kimi-k2.7-code' is
    stripped to bare '@cf/moonshotai/kimi-k2.7-code' before reaching graphify."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_api_key="cf-key",
        cloudflare_ai_account_id="acct123",
        graphify_llm_model="cloudflare_ai/@cf/moonshotai/kimi-k2.7-code",
    )
    env = manager._extract_env()
    assert env["GRAPHIFY_OPENAI_MODEL"] == "@cf/moonshotai/kimi-k2.7-code"


def test_manager_extract_env_lmstudio_strips_fcc_prefix(
    graphify_tmp_home: Path, graphify_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FCC-format model id 'lmstudio/qwen2.5-coder-7b-instruct' is stripped."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="lmstudio",
        graphify_llm_api_key="",
        lm_studio_base_url="http://localhost:1234/v1",
        graphify_llm_model="lmstudio/qwen2.5-coder-7b-instruct",
    )
    env = manager._extract_env()
    assert env["GRAPHIFY_OPENAI_MODEL"] == "qwen2.5-coder-7b-instruct"


def test_build_extract_args_strips_fcc_prefix(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    """--model gets the bare model id without FCC provider prefix."""
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_model="cloudflare_ai/@cf/moonshotai/kimi-k2.7-code",
    )
    project = _register_project(graphify_tmp_home)
    args = manager._build_extract_args(project, "extract")
    assert "--model" in args
    assert args[args.index("--model") + 1] == "@cf/moonshotai/kimi-k2.7-code"


def test_strip_fcc_model_prefix_bare_model_unchanged() -> None:
    from api.graphify.manager import _strip_fcc_model_prefix

    assert (
        _strip_fcc_model_prefix("@cf/meta/llama-3.3-70b-instruct-fp8-fast")
        == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    )


@pytest.mark.parametrize(
    ("backend", "attr", "env_key"),
    [
        ("gemini", "gemini_api_key", "GEMINI_API_KEY"),
        ("deepseek", "deepseek_api_key", "DEEPSEEK_API_KEY"),
        ("kimi", "kimi_api_key", "MOONSHOT_API_KEY"),
    ],
)
def test_manager_extract_env_reuses_provider_key_for_compat_backends(
    graphify_tmp_home: Path,
    graphify_settings: Any,
    backend: str,
    attr: str,
    env_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(env_key, raising=False)
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend=backend,
        graphify_llm_api_key="",
        **{attr: "provider-key"},
    )
    env = manager._extract_env()
    assert env[env_key] == "provider-key"


def test_build_extract_args_cloudflare_passes_openai_backend(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_model="@cf/meta/llama-3.3-70b",
    )
    project = GraphifyProject(path="/repo", name="repo")
    args = manager._build_extract_args(project, "extract")
    assert "--backend" in args
    assert args[args.index("--backend") + 1] == "openai"
    assert "--model" in args
    assert args[args.index("--model") + 1] == "@cf/meta/llama-3.3-70b"


def test_build_extract_args_code_only_skips_backend(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_code_only=True,
    )
    project = GraphifyProject(path="/repo", name="repo")
    args = manager._build_extract_args(project, "extract")
    assert "--code-only" in args
    assert "--backend" not in args


def test_build_extract_args_update_has_no_llm_flags(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(
        graphify_settings,
        graphify_llm_backend="cloudflare",
        graphify_llm_model="m",
    )
    project = GraphifyProject(path="/repo", name="repo")
    args = manager._build_extract_args(project, "update")
    assert "--backend" not in args
    assert "--model" not in args
    assert "--code-only" not in args


@pytest.mark.asyncio
async def test_manager_index_project_cloudflare_passes_backend_and_env(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    repo_path = graphify_tmp_home / "repo"
    repo_path.mkdir()
    project = _register_project(repo_path)
    manager = _build_manager(
        graphify_settings,
        graphify_python_path="/fake/python",
        graphify_llm_backend="cloudflare",
        graphify_llm_model="@cf/meta/llama-3.3-70b",
        cloudflare_ai_api_key="cf-key",
        cloudflare_ai_account_id="acct",
    )
    success_process = _async_process_mock(returncode=0)
    success_process.communicate = AsyncMock(return_value=(b"extracted", b""))

    with (
        patch("api.graphify.manager._is_graphify_importable", return_value=True),
        patch(
            "api.graphify.manager.GraphifyManager._ensure_graphify_llm_extra",
            new_callable=AsyncMock,
        ) as ensure_extra,
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=success_process,
        ) as create_subprocess,
    ):
        result = await manager.index_project(project)

    assert result["success"] is True
    ensure_extra.assert_awaited_once()
    args = create_subprocess.call_args.args
    assert "--backend" in args
    assert args[args.index("--backend") + 1] == "openai"
    assert "--model" in args
    assert args[args.index("--model") + 1] == "@cf/meta/llama-3.3-70b"
    env = create_subprocess.call_args.kwargs["env"]
    assert env["OPENAI_API_KEY"] == "cf-key"
    assert "accounts/acct/ai/v1" in env["OPENAI_BASE_URL"]


@pytest.mark.asyncio
async def test_ensure_graphify_llm_extra_installs_openai_when_missing(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_llm_backend="cloudflare")
    proc = _async_process_mock(returncode=0)
    with (
        patch("api.graphify.manager._is_module_importable", return_value=False),
        patch("api.graphify.manager._pip_path", return_value="/fake/pip"),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ) as create_subprocess,
    ):
        await manager._ensure_graphify_llm_extra("/fake/python")
    create_subprocess.assert_awaited_once()
    assert "graphifyy[openai]" in create_subprocess.call_args.args


@pytest.mark.asyncio
async def test_ensure_graphify_llm_extra_installs_anthropic_for_claude(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_llm_backend="claude")
    proc = _async_process_mock(returncode=0)
    with (
        patch("api.graphify.manager._is_module_importable", return_value=False),
        patch("api.graphify.manager._pip_path", return_value="/fake/pip"),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ) as create_subprocess,
    ):
        await manager._ensure_graphify_llm_extra("/fake/python")
    assert "graphifyy[anthropic]" in create_subprocess.call_args.args


@pytest.mark.asyncio
async def test_ensure_graphify_llm_extra_skips_when_sdk_present(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_llm_backend="cloudflare")
    with (
        patch("api.graphify.manager._is_module_importable", return_value=True),
        patch(
            "api.graphify.manager.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as create_subprocess,
    ):
        await manager._ensure_graphify_llm_extra("/fake/python")
    create_subprocess.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_graphify_llm_extra_noop_for_code_only(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(
        graphify_settings,
        graphify_code_only=True,
        graphify_llm_backend="cloudflare",
    )
    with patch("api.graphify.manager._is_module_importable") as is_module:
        await manager._ensure_graphify_llm_extra("/fake/python")
    is_module.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_graphify_llm_extra_noop_without_backend(
    graphify_tmp_home: Path, graphify_settings: Any
) -> None:
    manager = _build_manager(graphify_settings, graphify_llm_backend="")
    with patch("api.graphify.manager._is_module_importable") as is_module:
        await manager._ensure_graphify_llm_extra("/fake/python")
    is_module.assert_not_called()
