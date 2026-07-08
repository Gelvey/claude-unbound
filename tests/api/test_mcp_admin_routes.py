"""Tests for MCP Router admin API routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.admin_config import MASKED_SECRET
from api.app import create_app


def _local_client(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def _set_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def _seed_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "router_socket": "~/.mcp-router/sockets/router.sock",
                "router_pidfile": "~/.mcp-router/run/router.pid",
                "router_log": "~/.mcp-router/logs/router.log",
                "health_timeout_s": 30,
                "servers": {
                    "stripe": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@stripe/mcp@latest"],
                        "env": {"STRIPE_SECRET_KEY": "sk_live_real_secret"},
                        "port": 7101,
                    },
                    "remote-sse": {
                        "type": "sse",
                        "url": "http://127.0.0.1:9999/sse",
                        "port": 9999,
                    },
                    "composio": {
                        "type": "http",
                        "url": "https://connect.composio.dev/mcp",
                        "headers": {"x-consumer-api-key": "real_composio_key"},
                        "port": 7110,
                    },
                },
                "shared_servers": {
                    "remote-ssh": {
                        "type": "stdio",
                        "command": "node",
                        "args": ["server.js"],
                        "env": {"API_TOKEN": "shared_secret_token"},
                        "port": 7200,
                    },
                    "composio-shared": {
                        "type": "http",
                        "url": "https://connect.composio.dev/mcp",
                        "headers": {"x-consumer-api-key": "shared_composio_key"},
                        "port": 7201,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# GET /admin/api/mcp/config
# ---------------------------------------------------------------------------


def test_get_mcp_config_masks_env_secrets(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/mcp/config")

    assert response.status_code == 200
    body = response.json()
    assert "stripe" in body["servers"]
    stripe = body["servers"]["stripe"]
    assert stripe["env"]["STRIPE_SECRET_KEY"] == MASKED_SECRET
    assert body["router_socket"] == "~/.mcp-router/sockets/router.sock"


def test_get_mcp_config_masks_header_secrets(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/mcp/config")

    assert response.status_code == 200
    body = response.json()
    assert "composio" in body["servers"]
    composio = body["servers"]["composio"]
    assert composio["type"] == "http"
    assert composio["headers"]["x-consumer-api-key"] == MASKED_SECRET
    assert composio["url"] == "https://connect.composio.dev/mcp"


def test_get_mcp_config_masks_shared_server_secrets(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/mcp/config")

    assert response.status_code == 200
    body = response.json()
    assert "shared_servers" in body
    # Shared stdio server env should be masked
    ssh = body["shared_servers"]["remote-ssh"]
    assert ssh["env"]["API_TOKEN"] == MASKED_SECRET
    # Shared http server header should be masked
    composio_shared = body["shared_servers"]["composio-shared"]
    assert composio_shared["headers"]["x-consumer-api-key"] == MASKED_SECRET


def test_get_mcp_config_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    assert remote_client.get("/admin/api/mcp/config").status_code == 403


def test_get_mcp_config_returns_empty_when_missing(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/mcp/config")

    assert response.status_code == 200
    body = response.json()
    assert body["servers"] == {}


# ---------------------------------------------------------------------------
# POST /admin/api/mcp/config/apply
# ---------------------------------------------------------------------------


def test_apply_mcp_config_writes_file(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/apply",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "stripe": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y"],
                    "env": {"STRIPE_SECRET_KEY": MASKED_SECRET},
                    "port": 7101,
                },
                "new-backend": {
                    "type": "sse",
                    "url": "http://localhost:8000/sse",
                    "port": 8000,
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["restart_hint"] == "Restart the MCP Router tab to apply"
    # Verify file was written
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert "new-backend" in data["servers"]
    # Masked secret should be resolved to the original
    assert (
        data["servers"]["stripe"]["env"]["STRIPE_SECRET_KEY"] == "sk_live_real_secret"
    )


def test_apply_mcp_config_rejects_invalid(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/apply",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "bad": {"type": "stdio", "port": 7101},  # missing command
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_apply_mcp_config_resolves_masked_headers(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/apply",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "composio": {
                    "type": "http",
                    "url": "https://connect.composio.dev/mcp",
                    "headers": {"x-consumer-api-key": MASKED_SECRET},
                    "port": 7110,
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert (
        data["servers"]["composio"]["headers"]["x-consumer-api-key"]
        == "real_composio_key"
    )


def test_apply_mcp_config_resolves_shared_server_secrets(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/apply",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {},
            "shared_servers": {
                "remote-ssh": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["server.js"],
                    "env": {"API_TOKEN": MASKED_SECRET},
                    "port": 7200,
                },
                "composio-shared": {
                    "type": "http",
                    "url": "https://connect.composio.dev/mcp",
                    "headers": {"x-consumer-api-key": MASKED_SECRET},
                    "port": 7201,
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))
    # Masked shared secrets should be resolved to originals
    assert (
        data["shared_servers"]["remote-ssh"]["env"]["API_TOKEN"]
        == "shared_secret_token"
    )
    assert (
        data["shared_servers"]["composio-shared"]["headers"]["x-consumer-api-key"]
        == "shared_composio_key"
    )


def test_apply_mcp_config_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    assert remote_client.post("/admin/api/mcp/config/apply", json={}).status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/api/mcp/config/validate
# ---------------------------------------------------------------------------


def test_validate_mcp_config_valid(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/validate",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "test": {
                    "type": "stdio",
                    "command": "npx",
                    "port": 7200,
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_mcp_config_invalid(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/validate",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "test": {"type": "sse", "port": 7101},  # missing url
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("requires 'url'" in e for e in body["errors"])


def test_validate_mcp_config_http_valid(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/validate",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "composio": {
                    "type": "http",
                    "url": "https://connect.composio.dev/mcp",
                    "headers": {"x-consumer-api-key": "key"},
                    "port": 7110,
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_mcp_config_shared_server_duplicate_port(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/config/validate",
        json={
            "router_socket": "~/.mcp-router/sockets/router.sock",
            "router_pidfile": "~/.mcp-router/run/router.pid",
            "router_log": "~/.mcp-router/logs/router.log",
            "health_timeout_s": 30,
            "servers": {
                "local-backend": {
                    "type": "stdio",
                    "command": "npx",
                    "port": 7200,
                }
            },
            "shared_servers": {
                "shared-backend": {
                    "type": "stdio",
                    "command": "node",
                    "port": 7200,  # duplicate with local-backend
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("port 7200 already used" in e for e in body["errors"])


# ---------------------------------------------------------------------------
# GET /admin/api/mcp/status
# ---------------------------------------------------------------------------


def test_get_mcp_status_returns_not_running_when_socket_missing(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/mcp/status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False


def test_get_mcp_status_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    assert remote_client.get("/admin/api/mcp/status").status_code == 403


def test_get_mcp_status_returns_backends_when_socket_present(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    # Mock the socket I/O
    mock_status = {
        "running": True,
        "backends": [
            {
                "name": "stripe",
                "type": "stdio",
                "port": 7101,
                "activated": True,
                "tool_count": 3,
            },
            {
                "name": "remote-sse",
                "type": "sse",
                "port": 9999,
                "activated": False,
                "tool_count": 0,
            },
        ],
    }
    with patch("api.admin_routes.get_router_status", return_value=mock_status):
        response = _local_client(app).get("/admin/api/mcp/status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is True
    assert len(body["backends"]) == 2
    stripe = next(b for b in body["backends"] if b["name"] == "stripe")
    assert stripe["activated"] is True
    assert stripe["tool_count"] == 3


# ---------------------------------------------------------------------------
# POST /admin/api/mcp/composio/test
# ---------------------------------------------------------------------------


def test_composio_test_endpoint_success(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    async def mock_test_connection(api_key):
        return {
            "ok": True,
            "tool_count": 2,
            "tool_names": ["github_create_issue", "slack_send_message"],
        }

    with patch("api.admin_routes._test_composio_connection", mock_test_connection):
        response = _local_client(app).post(
            "/admin/api/mcp/composio/test",
            json={"api_key": "test_key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["tool_count"] == 2
    assert "github_create_issue" in body["tool_names"]
    assert "slack_send_message" in body["tool_names"]


def test_composio_test_endpoint_failure(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    async def mock_test_connection(api_key):
        raise ConnectionError("Connection refused")

    with patch("api.admin_routes._test_composio_connection", mock_test_connection):
        response = _local_client(app).post(
            "/admin/api/mcp/composio/test",
            json={"api_key": "bad_key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Connection refused" in body["error"]


def test_composio_test_endpoint_no_backend_no_key(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    # Seed config WITHOUT composio backend
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "router_socket": "~/.mcp-router/sockets/router.sock",
                "router_pidfile": "~/.mcp-router/run/router.pid",
                "router_log": "~/.mcp-router/logs/router.log",
                "health_timeout_s": 30,
                "servers": {
                    "stripe": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@stripe/mcp@latest"],
                        "env": {"STRIPE_SECRET_KEY": "sk_live_real_secret"},
                        "port": 7101,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/test",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "No Composio backend configured" in body["error"]


def test_composio_test_endpoint_uses_configured_key(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    captured_key = None

    async def mock_test_connection(api_key):
        nonlocal captured_key
        captured_key = api_key
        return {
            "ok": True,
            "tool_count": 1,
            "tool_names": ["test_tool"],
        }

    with patch("api.admin_routes._test_composio_connection", mock_test_connection):
        # No api_key in payload — should fall back to configured composio backend
        response = _local_client(app).post(
            "/admin/api/mcp/composio/test",
            json={},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert captured_key == "real_composio_key"


# ---------------------------------------------------------------------------
# POST /admin/api/mcp/composio/setup
# ---------------------------------------------------------------------------


def test_composio_setup_creates_backend(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    # Config without composio
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "router_socket": "~/.mcp-router/sockets/router.sock",
                "router_pidfile": "~/.mcp-router/run/router.pid",
                "router_log": "~/.mcp-router/logs/router.log",
                "health_timeout_s": 30,
                "servers": {
                    "stripe": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@stripe/mcp@latest"],
                        "env": {"STRIPE_SECRET_KEY": "sk_live_real_secret"},
                        "port": 7101,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": "new_composio_key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True

    # Verify the config file was updated
    saved = json.loads(config_file.read_text())
    assert "composio" in saved["servers"]
    composio = saved["servers"]["composio"]
    assert composio["type"] == "http"
    assert composio["url"] == "https://connect.composio.dev/mcp"
    assert composio["port"] == 7110
    assert composio["headers"]["x-consumer-api-key"] == "new_composio_key"


def test_composio_setup_updates_existing_key(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": "updated_key", "port": 7110},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True

    saved = json.loads((tmp_path / ".fcc" / "mcp_config.json").read_text())
    assert (
        saved["servers"]["composio"]["headers"]["x-consumer-api-key"] == "updated_key"
    )
    # Other servers should be preserved
    assert "stripe" in saved["servers"]
    assert "remote-sse" in saved["servers"]


def test_composio_setup_preserves_shared_servers(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": "new_key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True

    saved = json.loads((tmp_path / ".fcc" / "mcp_config.json").read_text())
    # Shared servers should be preserved
    assert "remote-ssh" in saved["shared_servers"]
    assert "composio-shared" in saved["shared_servers"]


def test_composio_setup_empty_key_rejected(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": ""},
    )

    assert response.status_code == 400
    assert "API key is required" in response.json()["detail"]


def test_composio_setup_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    response = remote_client.post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": "test"},
    )
    assert response.status_code == 403


def test_composio_test_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)

    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    response = remote_client.post(
        "/admin/api/mcp/composio/test",
        json={"api_key": "test"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Composio hardening: timeout, header preservation, error sanitization
# ---------------------------------------------------------------------------


def test_composio_setup_preserves_custom_headers_on_update(monkeypatch, tmp_path):
    """Updating the API key must not wipe user-added custom headers."""
    _set_home(monkeypatch, tmp_path)
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "router_socket": "~/.mcp-router/sockets/router.sock",
                "router_pidfile": "~/.mcp-router/run/router.pid",
                "router_log": "~/.mcp-router/logs/router.log",
                "health_timeout_s": 30,
                "servers": {
                    "composio": {
                        "type": "http",
                        "url": "https://connect.composio.dev/mcp",
                        "port": 7110,
                        "headers": {
                            "x-consumer-api-key": "old_key",
                            "x-composio-user-id": "user_abc",
                            "X-Trace-Id": "abc-123",
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/mcp/composio/setup",
        json={"api_key": "new_key"},
    )

    assert response.status_code == 200
    assert response.json()["applied"] is True

    saved = json.loads(config_file.read_text())
    headers = saved["servers"]["composio"]["headers"]
    assert headers["x-consumer-api-key"] == "new_key"
    # Custom headers must be preserved across the API key update.
    assert headers["x-composio-user-id"] == "user_abc"
    assert headers["X-Trace-Id"] == "abc-123"


def test_composio_test_falls_back_to_uppercase_header(monkeypatch, tmp_path):
    """Header lookup is case-insensitive: HTTP headers are not case-sensitive."""
    _set_home(monkeypatch, tmp_path)
    config_file = tmp_path / ".fcc" / "mcp_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "router_socket": "~/.mcp-router/sockets/router.sock",
                "router_pidfile": "~/.mcp-router/run/router.pid",
                "router_log": "~/.mcp-router/logs/router.log",
                "health_timeout_s": 30,
                "servers": {
                    "composio": {
                        "type": "http",
                        "url": "https://connect.composio.dev/mcp",
                        "port": 7110,
                        "headers": {"X-Consumer-Api-Key": "uppercase_key"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    captured: dict[str, str] = {}

    async def mock_test_connection(api_key: str):
        captured["api_key"] = api_key
        return {"ok": True, "tool_count": 0, "tool_names": []}

    with patch("api.admin_routes._test_composio_connection", mock_test_connection):
        response = _local_client(app).post(
            "/admin/api/mcp/composio/test",
            json={},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["api_key"] == "uppercase_key"


def test_composio_test_redacts_key_from_error(monkeypatch, tmp_path):
    """If a downstream exception echoes the API key back, it must be redacted."""
    _set_home(monkeypatch, tmp_path)
    _seed_config(tmp_path)
    app = create_app(lifespan_enabled=False)
    secret = "leaky_secret_token"

    async def mock_test_connection(api_key: str):
        raise RuntimeError(f"HTTP error for token {secret}: invalid")

    with patch("api.admin_routes._test_composio_connection", mock_test_connection):
        response = _local_client(app).post(
            "/admin/api/mcp/composio/test",
            json={"api_key": secret},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert secret not in body["error"]
    assert "[REDACTED]" in body["error"]


def test_composio_test_uses_httpx_timeout(monkeypatch):
    """_test_composio_connection must apply a non-None httpx timeout.

    Regression test: previously the helper constructed ``httpx.AsyncClient``
    without a timeout, which could hang indefinitely if the Composio server
    stalled. We stub the optional ``mcp`` imports (not installed in the
    runtime venv) so we can call into the real coroutine and inspect the
    kwargs httpx.AsyncClient received.
    """
    import asyncio
    import sys
    import types
    from typing import Any

    # Stub the optional MCP modules that _test_composio_connection imports.
    fake_mcp: Any = types.ModuleType("mcp")

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            # Accept whatever ClientSession is invoked with.
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            from types import SimpleNamespace

            return SimpleNamespace(tools=[])

    fake_mcp.ClientSession = _FakeSession
    fake_streamable: Any = types.ModuleType("mcp.client.streamable_http")

    class _FakeStream:
        def __init__(self, *args, **kwargs):
            # Accept whatever streamable_http_client is invoked with.
            pass

        async def __aenter__(self):
            return (object(), object(), lambda: None)

        async def __aexit__(self, *exc):
            return False

    fake_streamable.streamable_http_client = _FakeStream
    fake_client_pkg: Any = types.ModuleType("mcp.client")
    fake_client_pkg.streamable_http = fake_streamable
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_client_pkg)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", fake_streamable)

    # Intercept the AsyncClient constructor used by admin_routes.
    from api import admin_routes

    captured: dict[str, object] = {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(admin_routes.httpx, "AsyncClient", _FakeAsyncClient)
    result = asyncio.run(admin_routes._test_composio_connection("k"))

    timeout_value: object = captured.get("timeout")
    assert timeout_value is not None, "AsyncClient must receive a timeout"
    assert timeout_value == admin_routes.COMPOSIO_TEST_TIMEOUT_S
    # headers_kwarg is constructed by admin_routes as a dict[str, str].
    headers_kwarg = cast("dict[str, str]", captured["headers"])
    assert headers_kwarg.get("x-consumer-api-key") == "k"
    assert result["ok"] is True


def test_composio_helpers_unit():
    """Direct unit tests for the small helpers introduced for Composio."""
    from api.admin_routes import (
        COMPOSIO_API_KEY_HEADER,
        COMPOSIO_DEFAULT_URL,
        _build_composio_entry,
        _lookup_composio_api_key,
        _sanitize_composio_error,
    )

    entry = _build_composio_entry(api_key="abc", port=7110)
    assert entry["type"] == "http"
    assert entry["url"] == COMPOSIO_DEFAULT_URL
    assert entry["port"] == 7110
    assert entry["headers"][COMPOSIO_API_KEY_HEADER] == "abc"

    # Update preserves custom headers; only the API key changes.
    entry2 = _build_composio_entry(
        api_key="xyz",
        existing_headers={
            COMPOSIO_API_KEY_HEADER: "abc",
            "x-composio-user-id": "u1",
            "X-Trace-Id": "tr-1",
        },
    )
    headers = entry2["headers"]
    assert headers[COMPOSIO_API_KEY_HEADER] == "xyz"
    assert headers["x-composio-user-id"] == "u1"
    assert headers["X-Trace-Id"] == "tr-1"

    # Case-insensitive lookup matches HTTP convention.
    assert _lookup_composio_api_key({"X-Consumer-Api-Key": "upper_key"}) == "upper_key"
    assert _lookup_composio_api_key({"x-consumer-api-key": "lower_key"}) == "lower_key"
    assert (
        _lookup_composio_api_key({"X-CONSUMER-API-KEY": "shouty_key"}) == "shouty_key"
    )
    assert _lookup_composio_api_key({"unrelated": "v"}) == ""

    # Error sanitization: scrub the API key from downstream error texts.
    assert _sanitize_composio_error("secret", "msg without it") == "msg without it"
    assert _sanitize_composio_error("secret", "msg with secret inside") == (
        "msg with [REDACTED] inside"
    )
    assert _sanitize_composio_error("", "untouched") == "untouched"
