"""Tests for MCP Router admin API routes."""

from __future__ import annotations

import json
from pathlib import Path
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
