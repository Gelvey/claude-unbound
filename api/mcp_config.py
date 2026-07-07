"""MCP Router config: model, load, validate, write, and live status query."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import socket
import stat
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from config.paths import mcp_config_path

MASKED_SECRET = "********"
SOCKET_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class McpBackend(BaseModel):
    """One entry from the `servers` map in mcp_config.json."""

    name: str = Field(description="Backend name (valid identifier)")
    type: Literal["stdio", "sse", "http"] = Field(description="Backend transport type")
    port: int = Field(
        ge=1, le=65535, description="Local port (used by stdio supergateway)"
    )

    # stdio fields
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    # sse / http fields
    url: str | None = None
    headers: dict[str, str] = Field(
        default_factory=dict, description="HTTP headers for http backends"
    )

    @model_validator(mode="after")
    def _validate_type_fields(self) -> McpBackend:
        if self.type == "stdio" and not self.command:
            raise ValueError("stdio backend requires 'command'")
        if self.type == "sse" and not self.url:
            raise ValueError("sse backend requires 'url'")
        if self.type == "http" and not self.url:
            raise ValueError("http backend requires 'url'")
        return self


class SftpConfig(BaseModel):
    """SFTP configuration for shared MCP config."""

    host: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: Literal["password", "key"] = "password"
    password: str = ""
    private_key: str = ""
    remote_file_path: str = ""
    enabled: bool = False


class McpConfig(BaseModel):
    """Top-level mcp_config.json structure."""

    router_socket: str = "~/.mcp-router/sockets/router.sock"
    router_pidfile: str = "~/.mcp-router/run/router.pid"
    router_log: str = "~/.mcp-router/logs/router.log"
    health_timeout_s: int = 30
    servers: dict[str, McpBackend] = Field(default_factory=dict)
    shared_servers: dict[str, McpBackend] = Field(default_factory=dict)


class McpConfigResult(BaseModel):
    """Result of a config validation or apply operation."""

    valid: bool
    errors: list[str] = []
    applied: bool = False
    path: str | None = None
    restart_hint: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_config_path() -> Path:
    """Return the canonical config path, respecting MCP_ROUTER_CONFIG override."""
    return Path(os.environ.get("MCP_ROUTER_CONFIG", str(mcp_config_path())))


def _mask_env(env: dict[str, str]) -> dict[str, str]:
    """Mask non-empty env values (secrets)."""
    return {k: (MASKED_SECRET if v else "") for k, v in env.items()}


def _unmask_env(
    masked_env: dict[str, str], original_env: dict[str, str]
) -> dict[str, str]:
    """Resolve masked values: MASKED_SECRET means 'leave unchanged'."""
    result = {}
    for key, value in masked_env.items():
        if value == MASKED_SECRET:
            result[key] = original_env.get(key, "")
        else:
            result[key] = value
    return result


def _mask_headers(headers: dict[str, str]) -> dict[str, str]:
    """Mask non-empty header values (secrets)."""
    return {k: (MASKED_SECRET if v else "") for k, v in headers.items()}


def _unmask_headers(
    masked_headers: dict[str, str], original_headers: dict[str, str]
) -> dict[str, str]:
    """Resolve masked header values: MASKED_SECRET means 'leave unchanged'."""
    result = {}
    for key, value in masked_headers.items():
        if value == MASKED_SECRET:
            result[key] = original_headers.get(key, "")
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Load / validate / write
# ---------------------------------------------------------------------------


def load_mcp_config() -> tuple[McpConfig, Path]:
    """Load and parse the MCP config file. Returns (config, path)."""
    path = _resolve_config_path()
    if not path.exists():
        # Return empty config if file doesn't exist yet
        return McpConfig(), path
    data = json.loads(path.read_text(encoding="utf-8"))
    # Parse servers dict into McpBackend models, injecting name
    servers: dict[str, McpBackend] = {}
    for name, srv_data in data.get("servers", {}).items():
        srv_data["name"] = name
        servers[name] = McpBackend(**srv_data)
    shared_servers: dict[str, McpBackend] = {}
    for name, srv_data in data.get("shared_servers", {}).items():
        srv_data["name"] = name
        shared_servers[name] = McpBackend(**srv_data)
    config = McpConfig(
        router_socket=data.get("router_socket", "~/.mcp-router/sockets/router.sock"),
        router_pidfile=data.get("router_pidfile", "~/.mcp-router/run/router.pid"),
        router_log=data.get("router_log", "~/.mcp-router/logs/router.log"),
        health_timeout_s=data.get("health_timeout_s", 30),
        servers=servers,
        shared_servers=shared_servers,
    )
    return config, path


def validate_mcp_config(servers: dict[str, dict[str, Any]]) -> list[str]:
    """Validate a servers dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []
    names_seen: set[str] = set()
    ports_seen: set[int] = set()

    for name, srv_data in servers.items():
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", name):
            errors.append(
                f"server '{name}': name must start with a letter and contain only letters, digits, hyphens, and underscores"
            )
        if name in names_seen:
            errors.append(f"server '{name}': duplicate name")
        names_seen.add(name)

        srv_type = srv_data.get("type")
        if srv_type not in ("stdio", "sse", "http"):
            errors.append(f"server '{name}': type must be 'stdio', 'sse', or 'http'")
            continue

        if srv_type == "stdio" and not srv_data.get("command"):
            errors.append(f"server '{name}': stdio backend requires 'command'")
        if srv_type == "sse" and not srv_data.get("url"):
            errors.append(f"server '{name}': sse backend requires 'url'")
        if srv_type == "http" and not srv_data.get("url"):
            errors.append(f"server '{name}': http backend requires 'url'")

        port = srv_data.get("port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"server '{name}': port must be 1-65535")
        elif port in ports_seen:
            errors.append(
                f"server '{name}': port {port} already used by another server"
            )
        if isinstance(port, int):
            ports_seen.add(port)

    return errors


def write_mcp_config(
    router_socket: str,
    router_log: str,
    router_pidfile: str,
    health_timeout_s: int,
    servers: dict[str, dict[str, Any]],
    shared_servers: dict[str, dict[str, Any]] | None = None,
) -> McpConfigResult:
    """Validate and atomically write mcp_config.json (chmod 600)."""
    errors = validate_mcp_config(servers)
    if shared_servers:
        errors.extend(validate_mcp_config(shared_servers))
    if errors:
        return McpConfigResult(valid=False, errors=errors)

    path = _resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build the JSON structure (strip 'name' key from each server entry)
    output: dict[str, Any] = {
        "_comment": "MCP backend registry. Canonical location: ~/.fcc/mcp_config.json. Managed by Admin UI.",
        "router_socket": router_socket,
        "router_pidfile": router_pidfile,
        "router_log": router_log,
        "health_timeout_s": health_timeout_s,
        "servers": {},
        "shared_servers": {},
    }
    for name, srv_data in servers.items():
        entry = {k: v for k, v in srv_data.items() if k != "name"}
        output["servers"][name] = entry
    if shared_servers:
        for name, srv_data in shared_servers.items():
            entry = {k: v for k, v in srv_data.items() if k != "name"}
            output["shared_servers"][name] = entry

    # Atomic write
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # chmod 600

    return McpConfigResult(
        valid=True,
        applied=True,
        path=str(path),
        restart_hint="Restart the MCP Router tab to apply",
    )


# ---------------------------------------------------------------------------
# SFTP shared config helpers
# ---------------------------------------------------------------------------


def sftp_fetch_remote_config(sftp_config: SftpConfig) -> dict[str, Any]:
    """Connect via SFTP and read the remote mcp_config.json.

    Returns {"ok": True, "config": {...}} on success,
    or {"ok": False, "error": "..."} on failure.
    """
    import paramiko

    try:
        transport = paramiko.Transport((sftp_config.host, sftp_config.port))
        if sftp_config.auth_method == "key":
            key_file = paramiko.RSAKey.from_private_key(
                StringIO(sftp_config.private_key)
            )
            transport.connect(username=sftp_config.username, pkey=key_file)
        else:
            transport.connect(
                username=sftp_config.username, password=sftp_config.password
            )

        sftp = paramiko.SFTPClient.from_transport(transport)
        remote_path = sftp_config.remote_file_path

        try:
            with sftp.open(remote_path, "r") as f:
                data = json.loads(f.read().decode("utf-8"))
        except FileNotFoundError:
            return {"ok": False, "error": f"File not found: {remote_path}"}
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": f"Invalid JSON in {remote_path}: {exc}",
            }
        finally:
            sftp.close()
            transport.close()

        if "servers" not in data or not isinstance(data["servers"], dict):
            return {
                "ok": False,
                "error": "Remote config is missing a valid 'servers' section",
            }

        return {"ok": True, "config": data}

    except paramiko.AuthenticationException:
        return {"ok": False, "error": "SFTP authentication failed"}
    except paramiko.SSHException as exc:
        return {"ok": False, "error": f"SSH connection error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"Connection failed: {exc}"}


def validate_remote_mcp_config(data: dict[str, Any]) -> list[str]:
    """Validate a remote MCP config's server entries. Returns list of errors."""
    return validate_mcp_config(data.get("servers", {}))


# ---------------------------------------------------------------------------
# Live status (JSON-RPC over Unix socket)
# ---------------------------------------------------------------------------


async def _send_jsonrpc_async(sock_path: str, messages: list[dict[str, Any]]) -> str:
    """Send JSON-RPC messages to the router socket and return raw response.

    Uses asyncio with non-blocking I/O so the event loop is not blocked.
    """
    loop = asyncio.get_event_loop()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT_S)
    try:
        await loop.run_in_executor(None, s.connect, sock_path)
        for msg in messages:
            await loop.run_in_executor(
                None, s.sendall, (json.dumps(msg) + "\n").encode()
            )
        await asyncio.sleep(0.5)
        buf = b""
        try:
            while True:
                chunk = await loop.run_in_executor(None, s.recv, 8192)
                if not chunk:
                    break
                buf += chunk
                if buf.count(b"\n") >= len(messages):
                    break
        except TimeoutError:
            pass
        return buf.decode("utf-8", errors="replace")
    finally:
        s.close()


def _parse_jsonrpc_results(resp: str) -> list[dict[str, Any]]:
    """Extract parsed result payloads from JSON-RPC response lines."""
    results = []
    for line in resp.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "result" not in msg:
            continue
        content = msg["result"].get("content") or []
        if not content or not isinstance(content, list):
            continue
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if isinstance(text, str):
            with contextlib.suppress(json.JSONDecodeError):
                results.append(json.loads(text))
    return results


async def get_router_status(router_socket: str) -> dict[str, Any]:
    """Query the router for live backend status.

    Returns {running: false} if the socket doesn't exist or is unreachable,
    otherwise returns {running: true, backends: [...]}.
    """
    # Expand ~ in socket path
    expanded_socket = (
        router_socket.replace("~", str(Path.home()), 1)
        if router_socket.startswith("~")
        else router_socket
    )

    if not os.path.exists(expanded_socket):
        return {"running": False}

    try:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "admin-panel", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_servers", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_active_servers", "arguments": {}},
            },
        ]
        resp = await _send_jsonrpc_async(expanded_socket, messages)
        results = _parse_jsonrpc_results(resp)

        # list_servers result is first parsed result from tools/call (id=3)
        # list_active_servers is second (id=4)
        all_servers: list[dict[str, Any]] = []

        for result in results:
            if isinstance(result, list) and (
                all("tool_count" in item and "activated" in item for item in result)
                or not all("tool_names" in item for item in result)
            ):
                all_servers = result

        return {"running": True, "backends": all_servers}
    except Exception:
        return {"running": False}
