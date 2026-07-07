"""Tests for the Freebuff manager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.freebuff.manager import FreebuffManager


@pytest.fixture()
def tmp_credentials(tmp_path: Path):
    """Create a temporary credentials file with valid tokens."""
    creds_path = tmp_path / "credentials.json"
    data = {
        "default": {"authToken": "token-aaa"},
        "profile2": {"authToken": "token-bbb"},
    }
    creds_path.write_text(json.dumps(data), encoding="utf-8")
    return creds_path


@pytest.fixture()
def empty_credentials(tmp_path: Path):
    """Create a temporary credentials file with no tokens."""
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text("{}", encoding="utf-8")
    return creds_path


# ---------------------------------------------------------------------------
# Init tests
# ---------------------------------------------------------------------------


def test_init_defaults():
    manager = FreebuffManager()
    assert manager.port is None
    assert manager.base_url is None
    assert manager.is_running is False
    assert manager.method is None
    assert manager.auth_tokens == []
    assert manager.models == []


def test_init_with_port():
    manager = FreebuffManager(port=9999)
    assert manager.port == 9999


# ---------------------------------------------------------------------------
# Setup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_setup_no_binary(tmp_credentials: Path):
    manager = FreebuffManager(credentials_path=tmp_credentials)

    with patch(
        "providers.freebuff.manager.ensure_binary",
        new_callable=AsyncMock,
        return_value={
            "method": None,
            "available": False,
            "error": "No Docker or Go available",
        },
    ):
        result = await manager.setup()
        assert result["status"] == "error"
        assert "No Docker or Go available" in result["error"]


@pytest.mark.asyncio()
async def test_setup_no_credentials(tmp_path: Path):
    missing_creds = tmp_path / "nonexistent.json"
    manager = FreebuffManager(credentials_path=missing_creds)

    with patch(
        "providers.freebuff.manager.ensure_binary",
        new_callable=AsyncMock,
        return_value={
            "method": "docker",
            "available": True,
            "image": "ghcr.io/gelvey/freebuff2api:latest",
            "error": None,
        },
    ):
        result = await manager.setup()
        assert result["status"] == "error"
        assert "No Freebuff auth tokens found" in result["error"]


@pytest.mark.asyncio()
async def test_setup_success(tmp_credentials: Path, tmp_path: Path):
    manager = FreebuffManager(credentials_path=tmp_credentials, port=12345)

    with (
        patch(
            "providers.freebuff.manager.ensure_binary",
            new_callable=AsyncMock,
            return_value={
                "method": "docker",
                "available": True,
                "image": "ghcr.io/gelvey/freebuff2api:latest",
                "error": None,
            },
        ),
        patch(
            "providers.freebuff.manager.config_path",
            return_value=tmp_path / "config.json",
        ),
    ):
        result = await manager.setup()
        assert result["status"] == "ready"
        assert result["method"] == "docker"
        assert result["port"] == 12345
        assert result["token_count"] == 2
        assert result["base_url"] == "http://127.0.0.1:12345"


# ---------------------------------------------------------------------------
# Docker image preservation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_docker_image_preserved_across_skip_binary_ensure(
    tmp_credentials: Path, tmp_path: Path
):
    """Verify that _docker_image is not overwritten when skip_binary_ensure=True."""
    manager = FreebuffManager(credentials_path=tmp_credentials, port=12345)

    with (
        patch(
            "providers.freebuff.manager.ensure_binary",
            new_callable=AsyncMock,
            return_value={
                "method": "docker",
                "available": True,
                "image": "ghcr.io/gelvey/freebuff2api:latest",
                "error": None,
            },
        ),
        patch(
            "providers.freebuff.manager.config_path",
            return_value=tmp_path / "config.json",
        ),
    ):
        # First setup - should store the image
        await manager.setup()
        assert manager._docker_image == "ghcr.io/gelvey/freebuff2api:latest"

        # Mock binary_status to return no image (simulates skip_binary_ensure path)
        with patch(
            "providers.freebuff.manager.binary_status",
            return_value={
                "method": "docker",
                "docker_available": True,
                "go_available": False,
                "binary_exists": False,
                "binary_path": None,
                "version": None,
            },
        ):
            # Second setup with skip_binary_ensure=True should NOT overwrite image
            await manager.setup(skip_binary_ensure=True)
            assert manager._docker_image == "ghcr.io/gelvey/freebuff2api:latest"


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------


def test_status_not_running():
    manager = FreebuffManager()
    status = manager.status()
    assert status["running"] is False
    assert status["method"] is None
    assert status["port"] is None
    assert status["auth_token_count"] == 0
    assert status["model_count"] == 0


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_health_check_no_base_url():
    manager = FreebuffManager()
    with patch(
        "providers.freebuff.manager.check_container_running",
        new_callable=AsyncMock,
        return_value={
            "running": False,
            "container_id": None,
            "status": "not_found",
            "host_port": None,
            "error": None,
            "requires_sudo": False,
        },
    ):
        result = await manager.health_check()
    assert result["status"] == "not_configured"


@pytest.mark.asyncio()
async def test_health_check_healthy():
    manager = FreebuffManager(port=8080)
    manager._base_url = "http://127.0.0.1:8080"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ok": True,
        "uptime_sec": 120,
        "token_state": [],
    }

    with patch("providers.freebuff.manager.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await manager.health_check()
        assert result["status"] == "healthy"
        assert result["uptime_sec"] == 120


# ---------------------------------------------------------------------------
# Model discovery tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_discover_models_no_base_url():
    manager = FreebuffManager()
    with patch(
        "providers.freebuff.manager.check_container_running",
        new_callable=AsyncMock,
        return_value={
            "running": False,
            "container_id": None,
            "status": "not_found",
            "host_port": None,
            "error": None,
            "requires_sudo": False,
        },
    ):
        models = await manager.discover_models()
    assert models == []


@pytest.mark.asyncio()
async def test_discover_models_success():
    manager = FreebuffManager(port=8080)
    manager._base_url = "http://127.0.0.1:8080"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "object": "list",
        "data": [
            {"id": "minimax/minimax-m2.7", "object": "model"},
            {"id": "z-ai/glm-5.1", "object": "model"},
        ],
    }

    with patch("providers.freebuff.manager.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        models = await manager.discover_models()
        assert len(models) == 2
        assert models[0]["id"] == "minimax/minimax-m2.7"
        assert manager.models == models


# ---------------------------------------------------------------------------
# _remove_stale_container tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_remove_stale_container_success_on_first_try() -> None:
    """docker rm -f returns 0 → no sudo retry needed."""
    manager = FreebuffManager()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stderr = None
    mock_proc.wait = AsyncMock()

    with patch(
        "providers.freebuff.manager.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=mock_proc,
    ) as mock_exec:
        await manager._remove_stale_container()

    # Only one call (no sudo retry)
    mock_exec.assert_awaited_once()
    args = mock_exec.call_args[0]
    assert "sudo" not in args


@pytest.mark.asyncio()
async def test_remove_stale_container_no_sudo_on_non_permission_error() -> None:
    """When docker rm fails with non-permission error (e.g. container not found),
    the method should NOT fall through to sudo."""
    manager = FreebuffManager()
    mock_proc = MagicMock()
    mock_proc.returncode = 1  # non-zero, but not permission denied
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.read = AsyncMock(
        return_value=b"Error: no such container: freebuff2api"
    )
    mock_proc.wait = AsyncMock()

    with patch(
        "providers.freebuff.manager.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=mock_proc,
    ) as mock_exec:
        await manager._remove_stale_container()

    # Only one call — should NOT retry with sudo for non-permission failures
    mock_exec.assert_awaited_once()
    args = mock_exec.call_args[0]
    assert "sudo" not in args


@pytest.mark.asyncio()
async def test_remove_stale_container_retries_sudo_on_permission_denied() -> None:
    """When docker rm fails with permission denied, retry with sudo."""
    manager = FreebuffManager()
    mock_proc_fail = MagicMock()
    mock_proc_fail.returncode = 13
    mock_proc_fail.stderr = AsyncMock()
    mock_proc_fail.stderr.read = AsyncMock(
        return_value=b"permission denied while trying to connect to Docker"
    )
    mock_proc_fail.wait = AsyncMock()

    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.stderr = None
    mock_proc_ok.wait = AsyncMock()

    with patch(
        "providers.freebuff.manager.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        side_effect=[mock_proc_fail, mock_proc_ok],
    ) as mock_exec:
        await manager._remove_stale_container()

    # Two calls — first without sudo, second with sudo
    assert mock_exec.await_count == 2
    second_call_args = mock_exec.call_args_list[1][0]
    assert "sudo" in second_call_args


@pytest.mark.asyncio()
async def test_remove_stale_container_returns_on_file_not_found() -> None:
    """When docker binary is not found, the method returns without error."""
    manager = FreebuffManager()

    with patch(
        "providers.freebuff.manager.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        side_effect=FileNotFoundError("docker not found"),
    ):
        # Should not raise
        await manager._remove_stale_container()
