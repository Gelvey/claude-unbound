"""Tests for api.mcp_config — model validation, load/write, secret masking."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from api.mcp_config import (
    MASKED_SECRET,
    McpBackend,
    _mask_headers,
    _unmask_headers,
    load_mcp_config,
    validate_mcp_config,
    write_mcp_config,
)


def _set_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestMcpBackendModel:
    def test_stdio_requires_command(self) -> None:
        with pytest.raises(ValueError, match="stdio backend requires 'command'"):
            McpBackend(name="test", type="stdio", port=7101)

    def test_sse_requires_url(self) -> None:
        with pytest.raises(ValueError, match="sse backend requires 'url'"):
            McpBackend(name="test", type="sse", port=9999)

    def test_stdio_valid(self) -> None:
        backend = McpBackend(
            name="stripe",
            type="stdio",
            command="npx",
            args=["-y", "@stripe/mcp@latest"],
            env={"STRIPE_SECRET_KEY": "sk_test"},
            port=7101,
        )
        assert backend.name == "stripe"
        assert backend.type == "stdio"
        assert backend.command == "npx"
        assert backend.port == 7101

    def test_sse_valid(self) -> None:
        backend = McpBackend(
            name="remote",
            type="sse",
            url="http://127.0.0.1:9999/sse",
            port=9999,
        )
        assert backend.name == "remote"
        assert backend.type == "sse"
        assert backend.url == "http://127.0.0.1:9999/sse"

    def test_http_requires_url(self) -> None:
        with pytest.raises(ValueError, match="http backend requires 'url'"):
            McpBackend(name="test", type="http", port=7110)

    def test_http_valid(self) -> None:
        backend = McpBackend(
            name="composio",
            type="http",
            url="https://connect.composio.dev/mcp",
            headers={"x-consumer-api-key": "secret"},
            port=7110,
        )
        assert backend.name == "composio"
        assert backend.type == "http"
        assert backend.url == "https://connect.composio.dev/mcp"
        assert backend.headers == {"x-consumer-api-key": "secret"}

    def test_http_empty_headers_default(self) -> None:
        backend = McpBackend(
            name="test",
            type="http",
            url="http://localhost/mcp",
            port=7110,
        )
        assert backend.headers == {}

    def test_port_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            McpBackend(name="test", type="sse", url="http://localhost/sse", port=0)

        with pytest.raises(ValueError):
            McpBackend(name="test", type="sse", url="http://localhost/sse", port=70000)


class TestValidateMcpConfig:
    def test_empty_servers_valid(self) -> None:
        assert validate_mcp_config({}) == []

    def test_unique_names_and_ports(self) -> None:
        servers = {
            "stripe": {"type": "stdio", "command": "npx", "port": 7101},
            "resend": {"type": "stdio", "command": "npx", "port": 7102},
        }
        assert validate_mcp_config(servers) == []

    def test_duplicate_name(self) -> None:
        servers = {
            "stripe": {"type": "stdio", "command": "npx", "port": 7101},
        }
        # Duplicate names can't happen in a dict, but test the validator logic
        errors = validate_mcp_config(servers)
        assert errors == []

    def test_duplicate_port(self) -> None:
        servers = {
            "stripe": {"type": "stdio", "command": "npx", "port": 7101},
            "resend": {"type": "stdio", "command": "npx", "port": 7101},
        }
        errors = validate_mcp_config(servers)
        assert any("port 7101 already used" in e for e in errors)

    def test_stdio_needs_command(self) -> None:
        servers = {
            "test": {"type": "stdio", "port": 7101},
        }
        errors = validate_mcp_config(servers)
        assert any("requires 'command'" in e for e in errors)

    def test_sse_needs_url(self) -> None:
        servers = {
            "test": {"type": "sse", "port": 7101},
        }
        errors = validate_mcp_config(servers)
        assert any("requires 'url'" in e for e in errors)

    def test_http_needs_url(self) -> None:
        servers = {
            "test": {"type": "http", "port": 7110},
        }
        errors = validate_mcp_config(servers)
        assert any("requires 'url'" in e for e in errors)

    def test_http_valid_config(self) -> None:
        servers = {
            "composio": {
                "type": "http",
                "url": "https://connect.composio.dev/mcp",
                "headers": {"x-consumer-api-key": "key"},
                "port": 7110,
            },
        }
        assert validate_mcp_config(servers) == []

    def test_invalid_type(self) -> None:
        servers = {
            "test": {"type": "ftp", "port": 7101},
        }
        errors = validate_mcp_config(servers)
        assert any("type must be" in e for e in errors)

    def test_invalid_port(self) -> None:
        servers = {
            "test": {"type": "sse", "url": "http://x", "port": 0},
        }
        errors = validate_mcp_config(servers)
        assert any("port must be 1-65535" in e for e in errors)


# ---------------------------------------------------------------------------
# Atomic write + chmod 600
# ---------------------------------------------------------------------------


class TestWriteMcpConfig:
    def test_writes_valid_config(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
        config_file = tmp_path / ".fcc" / "mcp_config.json"
        config_file.parent.mkdir(parents=True)

        result = write_mcp_config(
            router_socket="~/.mcp-router/sockets/router.sock",
            router_log="~/.mcp-router/logs/router.log",
            router_pidfile="~/.mcp-router/run/router.pid",
            health_timeout_s=30,
            servers={
                "stripe": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@stripe/mcp@latest"],
                    "env": {"STRIPE_SECRET_KEY": "sk_test"},
                    "port": 7101,
                }
            },
        )

        assert result.valid is True
        assert result.applied is True
        assert result.restart_hint == "Restart the MCP Router tab to apply"
        assert config_file.exists()
        text = config_file.read_text(encoding="utf-8")
        data = json.loads(text)
        assert "stripe" in data["servers"]
        assert data["servers"]["stripe"]["command"] == "npx"
        # Verify chmod 600
        mode = os.stat(config_file).st_mode
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR  # owner rw only
        assert not (mode & stat.S_IRGRP)  # no group read
        assert not (mode & stat.S_IROTH)  # no other read

    def test_rejects_invalid_config(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)

        result = write_mcp_config(
            router_socket="~/.mcp-router/sockets/router.sock",
            router_log="~/.mcp-router/logs/router.log",
            router_pidfile="~/.mcp-router/run/router.pid",
            health_timeout_s=30,
            servers={
                "bad": {"type": "stdio", "port": 7101},  # missing command
            },
        )

        assert result.valid is False
        assert result.applied is False
        assert len(result.errors) > 0

    def test_strips_name_key_from_output(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
        config_file = tmp_path / ".fcc" / "mcp_config.json"
        config_file.parent.mkdir(parents=True)

        write_mcp_config(
            router_socket="~/.mcp-router/sockets/router.sock",
            router_log="~/.mcp-router/logs/router.log",
            router_pidfile="~/.mcp-router/run/router.pid",
            health_timeout_s=30,
            servers={
                "stripe": {
                    "name": "stripe",
                    "type": "stdio",
                    "command": "npx",
                    "port": 7101,
                }
            },
        )

        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert "name" not in data["servers"]["stripe"]

    def test_writes_shared_servers(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
        config_file = tmp_path / ".fcc" / "mcp_config.json"
        config_file.parent.mkdir(parents=True)

        result = write_mcp_config(
            router_socket="~/.mcp-router/sockets/router.sock",
            router_log="~/.mcp-router/logs/router.log",
            router_pidfile="~/.mcp-router/run/router.pid",
            health_timeout_s=30,
            servers={},
            shared_servers={
                "remote-ssh": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["server.js"],
                    "env": {"API_TOKEN": "secret_token"},
                    "port": 7200,
                }
            },
        )

        assert result.valid is True
        assert result.applied is True
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert "remote-ssh" in data["shared_servers"]
        assert (
            data["shared_servers"]["remote-ssh"]["env"]["API_TOKEN"] == "secret_token"
        )


# ---------------------------------------------------------------------------
# Secret masking on read
# ---------------------------------------------------------------------------


class TestSecretMasking:
    def test_mask_env_masks_values(self, monkeypatch, tmp_path: Path) -> None:
        from api.mcp_config import _mask_env

        result = _mask_env({"KEY": "secret-value", "EMPTY": ""})
        assert result == {"KEY": MASKED_SECRET, "EMPTY": ""}

    def test_unmask_env_leaves_masked_unchanged(self) -> None:
        from api.mcp_config import _unmask_env

        original = {"KEY": "real-secret", "OTHER": "other-val"}
        masked = {"KEY": MASKED_SECRET, "OTHER": "new-val", "NEW_KEY": "brand-new"}
        result = _unmask_env(masked, original)
        assert result == {
            "KEY": "real-secret",
            "OTHER": "new-val",
            "NEW_KEY": "brand-new",
        }

    def test_unmask_env_empty_masked_becomes_empty(self) -> None:
        from api.mcp_config import _unmask_env

        original = {"KEY": "real-secret"}
        masked = {"KEY": ""}
        result = _unmask_env(masked, original)
        assert result == {"KEY": ""}

    def test_mask_headers_masks_values(self) -> None:
        result = _mask_headers({"x-consumer-api-key": "secret-key", "empty-header": ""})
        assert result == {
            "x-consumer-api-key": MASKED_SECRET,
            "empty-header": "",
        }

    def test_unmask_headers_leaves_masked_unchanged(self) -> None:
        original = {"x-consumer-api-key": "real-key", "other": "other-val"}
        masked = {
            "x-consumer-api-key": MASKED_SECRET,
            "other": "new-val",
            "new-header": "brand-new",
        }
        result = _unmask_headers(masked, original)
        assert result == {
            "x-consumer-api-key": "real-key",
            "other": "new-val",
            "new-header": "brand-new",
        }

    def test_unmask_headers_empty_masked_becomes_empty(self) -> None:
        original = {"x-consumer-api-key": "real-key"}
        masked = {"x-consumer-api-key": ""}
        result = _unmask_headers(masked, original)
        assert result == {"x-consumer-api-key": ""}


# ---------------------------------------------------------------------------
# Load MCP config
# ---------------------------------------------------------------------------


class TestLoadMcpConfig:
    def test_load_existing_config(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
        config_file = tmp_path / ".fcc" / "mcp_config.json"
        config_file.parent.mkdir(parents=True)
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
                            "args": ["-y"],
                            "env": {"STRIPE_SECRET_KEY": "sk_test"},
                            "port": 7101,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        config, path = load_mcp_config()
        assert path == config_file
        assert "stripe" in config.servers
        assert config.servers["stripe"].command == "npx"
        assert config.servers["stripe"].env["STRIPE_SECRET_KEY"] == "sk_test"

    def test_load_missing_config_returns_empty(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)

        config, _path = load_mcp_config()
        assert config.servers == {}
        assert config.health_timeout_s == 30

    def test_load_respects_env_override(self, monkeypatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_config.json"
        custom.write_text(
            json.dumps({"servers": {}, "health_timeout_s": 10}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MCP_ROUTER_CONFIG", str(custom))

        config, path = load_mcp_config()
        assert path == custom
        assert config.health_timeout_s == 10

    def test_load_shared_servers(self, monkeypatch, tmp_path: Path) -> None:
        _set_home(monkeypatch, tmp_path)
        monkeypatch.delenv("MCP_ROUTER_CONFIG", raising=False)
        config_file = tmp_path / ".fcc" / "mcp_config.json"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(
            json.dumps(
                {
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
                            "env": {"API_TOKEN": "secret_token"},
                            "port": 7200,
                        },
                        "composio-shared": {
                            "type": "http",
                            "url": "https://connect.composio.dev/mcp",
                            "headers": {"x-consumer-api-key": "key123"},
                            "port": 7201,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        config, _path = load_mcp_config()
        assert "remote-ssh" in config.shared_servers
        assert config.shared_servers["remote-ssh"].command == "node"
        assert config.shared_servers["remote-ssh"].env["API_TOKEN"] == "secret_token"
        assert "composio-shared" in config.shared_servers
        assert config.shared_servers["composio-shared"].type == "http"
        assert (
            config.shared_servers["composio-shared"].headers["x-consumer-api-key"]
            == "key123"
        )
