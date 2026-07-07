"""Local admin UI routes and APIs."""

from __future__ import annotations

import inspect
import ipaddress
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config.settings import Settings
from config.settings import get_settings as get_cached_settings
from providers.registry import ProviderRegistry, create_freebuff_manager

from .admin_config import (
    FIELD_BY_KEY,
    load_config_response,
    provider_config_status,
    read_claude_permissions_setting,
    validate_updates,
    write_claude_permissions_setting,
    write_managed_env,
)
from .admin_urls import local_admin_url
from .mcp_config import (
    MASKED_SECRET as MCP_MASKED_SECRET,
)
from .mcp_config import (
    SftpConfig,
    get_router_status,
    load_mcp_config,
    sftp_fetch_remote_config,
    validate_remote_mcp_config,
    write_mcp_config,
)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent / "admin_static"
LOCAL_PROVIDER_PATHS = {
    "lmstudio": "/models",
    "llamacpp": "/models",
    "ollama": "/api/tags",
}


class AdminConfigPayload(BaseModel):
    """Partial config update submitted by the admin UI."""

    values: dict[str, Any] = Field(default_factory=dict)


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _origin_is_local(origin: str | None) -> bool:
    if not origin:
        return True
    parsed = urlsplit(origin)
    return _is_loopback_host(parsed.hostname)


def require_loopback_admin(request: Request) -> None:
    """Allow admin access only from the local machine."""

    client_host = request.client.host if request.client else None
    if not _is_loopback_host(client_host):
        raise HTTPException(status_code=403, detail="Admin UI is local-only")

    origin = request.headers.get("origin")
    if not _origin_is_local(origin):
        raise HTTPException(status_code=403, detail="Admin UI is local-only")


def _asset_response(filename: str) -> FileResponse:
    path = STATIC_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Admin asset not found")
    return FileResponse(path)


@router.get("/admin", include_in_schema=False)
async def admin_page(request: Request):
    require_loopback_admin(request)
    return _asset_response("index.html")


@router.get("/admin/assets/{filename}", include_in_schema=False)
async def admin_asset(filename: str, request: Request):
    require_loopback_admin(request)
    if filename not in {"admin.css", "admin.js", "favicon.svg"}:
        raise HTTPException(status_code=404, detail="Admin asset not found")
    return _asset_response(filename)


@router.get("/admin/api/config")
async def get_admin_config(request: Request):
    require_loopback_admin(request)
    return load_config_response()


@router.post("/admin/api/config/validate")
async def validate_admin_config(payload: AdminConfigPayload, request: Request):
    require_loopback_admin(request)
    return validate_updates(_filtered_values(payload.values))


@router.post("/admin/api/config/apply")
async def apply_admin_config(
    payload: AdminConfigPayload,
    request: Request,
    background_tasks: BackgroundTasks,
):
    require_loopback_admin(request)
    filtered = _filtered_values(payload.values)
    # Handle Claude permissions via settings.json
    permission_key = "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"
    permission_value = filtered.pop(permission_key, None)
    result = write_managed_env(filtered)
    if not result["applied"]:
        return result

    if permission_value is not None:
        target_enabled = str(permission_value).lower() == "true"
        if target_enabled != read_claude_permissions_setting():
            write_claude_permissions_setting(target_enabled)

    get_cached_settings.cache_clear()
    restart = _restart_metadata(result["pending_fields"], request)
    result["restart"] = restart
    if restart["required"] and restart["automatic"]:
        callback = request.app.state.admin_restart_callback
        background_tasks.add_task(_invoke_admin_restart_callback, callback)
        request.app.state.admin_pending_fields = []
        return result

    old_registry = getattr(request.app.state, "provider_registry", None)
    if isinstance(old_registry, ProviderRegistry):
        await old_registry.cleanup()
    request.app.state.provider_registry = ProviderRegistry()
    request.app.state.admin_pending_fields = result["pending_fields"]
    return result


@router.get("/admin/api/status")
async def admin_status(request: Request):
    require_loopback_admin(request)
    settings = get_cached_settings()
    registry = getattr(request.app.state, "provider_registry", None)
    cached_models: dict[str, list[str]] = {}
    if isinstance(registry, ProviderRegistry):
        cached_models = {
            provider_id: sorted(model_ids)
            for provider_id, model_ids in registry.cached_model_ids().items()
        }
    return {
        "status": "running",
        "host": settings.host,
        "port": settings.port,
        "model": settings.model,
        "provider": settings.provider_type,
        "pending_fields": getattr(request.app.state, "admin_pending_fields", []),
        "provider_status": provider_config_status(),
        "cached_models": cached_models,
    }


@router.get("/admin/api/providers/local-status")
async def local_provider_status(request: Request):
    require_loopback_admin(request)
    config = load_config_response()
    values = {field["key"]: field["value"] for field in config["fields"]}
    checks = []
    for provider_id, path in LOCAL_PROVIDER_PATHS.items():
        base_url = _local_provider_url(provider_id, values)
        checks.append(await _check_local_provider(provider_id, base_url, path))
    return {"providers": checks}


@router.post("/admin/api/providers/{provider_id}/test")
async def test_provider(provider_id: str, request: Request):
    require_loopback_admin(request)
    settings = get_cached_settings()
    registry = getattr(request.app.state, "provider_registry", None)
    if not isinstance(registry, ProviderRegistry):
        registry = ProviderRegistry()
        request.app.state.provider_registry = registry
    # Force a fresh provider instance for freebuff — its port is dynamic
    # and the cached instance may have a stale base_url after restart.
    # evict() calls cleanup() on the old provider to release connections.
    await registry.evict(provider_id)
    try:
        provider = registry.get(provider_id, settings)
        # Capture the models endpoint URL before the request for error diagnostics
        request_url = None
        models_endpoint = getattr(provider, "_models_endpoint", None)
        if callable(models_endpoint):
            request_url = models_endpoint()
        infos = await provider.list_model_infos()
    except httpx.HTTPStatusError as exc:
        error_message = _extract_http_error_message(exc)
        result: dict[str, Any] = {
            "provider_id": provider_id,
            "ok": False,
            "error_type": type(exc).__name__,
            "status_code": exc.response.status_code,
            "error_message": error_message,
        }
        if request_url:
            result["request_url"] = request_url
        return result
    except Exception as exc:
        error_result: dict[str, Any] = {
            "provider_id": provider_id,
            "ok": False,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        if request_url:
            error_result["request_url"] = request_url
        return error_result
    registry.cache_model_infos(provider_id, infos)
    return {
        "provider_id": provider_id,
        "ok": True,
        "models": sorted(info.model_id for info in infos),
    }


@router.post("/admin/api/models/refresh")
async def refresh_models(request: Request):
    require_loopback_admin(request)
    settings = get_cached_settings()
    registry = getattr(request.app.state, "provider_registry", None)
    if not isinstance(registry, ProviderRegistry):
        registry = ProviderRegistry()
        request.app.state.provider_registry = registry
    await registry.refresh_model_list_cache(settings)
    return {
        "cached_models": {
            provider_id: sorted(model_ids)
            for provider_id, model_ids in registry.cached_model_ids().items()
        }
    }


def _extract_http_error_message(exc: httpx.HTTPStatusError) -> str:
    """Extract a human-readable error message from an HTTP status error response."""
    try:
        body = exc.response.json()
        if isinstance(body, dict):
            # Cloudflare API error format: {"success": false, "errors": [...]}
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    return first_error.get("message", str(first_error))
                return str(first_error)
            # OpenAI-compatible error format: {"error": {"message": "..."}}
            error = body.get("error")
            if isinstance(error, dict):
                return error.get("message", str(error))
            # Generic error format: {"message": "..."}
            message = body.get("message")
            if isinstance(message, str):
                return message
    except Exception:
        pass
    # Fallback to response text (truncated)
    text = exc.response.text[:200] if exc.response.text else ""
    return text or f"HTTP {exc.response.status_code}"


def _filtered_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key in FIELD_BY_KEY}


async def _invoke_admin_restart_callback(callback: Any) -> None:
    result = callback()
    if inspect.isawaitable(result):
        await result


def _restart_metadata(fields: list[str], request: Request) -> dict[str, Any]:
    callback = getattr(request.app.state, "admin_restart_callback", None)
    automatic = bool(fields and callable(callback))
    return {
        "required": bool(fields),
        "automatic": automatic,
        "admin_url": _next_admin_url() if automatic else None,
        "fields": fields,
    }


def _next_admin_url() -> str:
    fields = {
        field["key"]: field["value"] for field in load_config_response()["fields"]
    }
    settings = Settings.model_construct(
        host=fields.get("HOST") or "0.0.0.0",
        port=int(fields.get("PORT") or 8082),
    )
    return local_admin_url(settings)


def _local_provider_url(provider_id: str, values: dict[str, str]) -> str:
    if provider_id == "lmstudio":
        return values.get("LM_STUDIO_BASE_URL", "")
    if provider_id == "llamacpp":
        return values.get("LLAMACPP_BASE_URL", "")
    if provider_id == "ollama":
        return values.get("OLLAMA_BASE_URL", "")
    return ""


async def _check_local_provider(
    provider_id: str, base_url: str, path: str
) -> dict[str, Any]:
    clean_url = base_url.strip().rstrip("/")
    if not clean_url:
        return {
            "provider_id": provider_id,
            "status": "missing_url",
            "label": "Missing URL",
            "base_url": base_url,
        }

    url = f"{clean_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(url)
        ok = 200 <= response.status_code < 300
        return {
            "provider_id": provider_id,
            "status": "reachable" if ok else "offline",
            "label": "Reachable" if ok else "Offline",
            "base_url": base_url,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {
            "provider_id": provider_id,
            "status": "offline",
            "label": "Offline",
            "base_url": base_url,
            "error_type": type(exc).__name__,
        }


# ---------------------------------------------------------------------------
# Freebuff2API admin routes
# ---------------------------------------------------------------------------


def _get_freebuff_manager(request: Request):
    """Return the shared FreebuffManager singleton (stored on app.state)."""
    manager = getattr(request.app.state, "freebuff_manager", None)
    if manager is None:
        settings = get_cached_settings()
        manager = create_freebuff_manager(
            credentials_path=settings.freebuff_credentials_path or None,
        )
        request.app.state.freebuff_manager = manager
    return manager


@router.get("/admin/api/freebuff/status")
async def freebuff_status(request: Request):
    """Return Freebuff2API status for the admin panel."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    return await manager.get_actual_status()


@router.post("/admin/api/freebuff/setup")
async def freebuff_setup(request: Request):
    """Set up Freebuff2API (ensure binary, read credentials, generate config)."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    return await manager.setup()


@router.post("/admin/api/freebuff/start")
async def freebuff_start(request: Request):
    """Start the Freebuff2API instance."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    success = await manager.start()
    result: dict[str, Any] = {
        "success": success,
        "status": manager.status(),
    }
    if not success and manager.last_error:
        result["error"] = manager.last_error
    return result


@router.post("/admin/api/freebuff/stop")
async def freebuff_stop(request: Request):
    """Stop the Freebuff2API instance."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    await manager.stop()
    return {"success": True}


@router.post("/admin/api/freebuff/restart")
async def freebuff_restart(request: Request):
    """Restart the Freebuff2API instance."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    success = await manager.restart()
    return {
        "success": success,
        "status": manager.status(),
    }


@router.get("/admin/api/freebuff/health")
async def freebuff_health(request: Request):
    """Check Freebuff2API health (probes /healthz endpoint)."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    return await manager.health_check()


@router.get("/admin/api/freebuff/models")
async def freebuff_models(request: Request):
    """Discover available models from Freebuff2API."""
    require_loopback_admin(request)
    manager = _get_freebuff_manager(request)
    models = await manager.discover_models()
    return {"models": models}


# ---------------------------------------------------------------------------
# Claude permissions settings (backed by ~/.claude/settings.json)
# ---------------------------------------------------------------------------


@router.get("/admin/settings/claude_dangerously_skip_permissions")
async def read_claude_dangerously_skip_permissions(request: Request):
    """Read the current dangerously_skip_permissions value from ~/.claude/settings.json."""
    require_loopback_admin(request)
    return {"current_value": read_claude_permissions_setting()}


class PermissionsPayload(BaseModel):
    """Value to write for claude_dangerously_skip_permissions."""

    value: bool


@router.post("/admin/settings/claude_dangerously_skip_permissions")
async def write_claude_dangerously_skip_permissions(
    payload: PermissionsPayload, request: Request
):
    """Write dangerously_skip_permissions to ~/.claude/settings.json."""
    require_loopback_admin(request)
    try:
        write_claude_permissions_setting(payload.value)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# MCP Router admin routes
# ---------------------------------------------------------------------------


class McpConfigPayload(BaseModel):
    """MCP config update submitted by the admin UI."""

    router_socket: str = "~/.mcp-router/sockets/router.sock"
    router_pidfile: str = "~/.mcp-router/run/router.pid"
    router_log: str = "~/.mcp-router/logs/router.log"
    health_timeout_s: int = 30
    servers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    shared_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _mask_mcp_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config with env and header secrets masked for display."""
    masked = dict(config)
    masked["servers"] = _mask_server_dict(config.get("servers", {}))
    masked["shared_servers"] = _mask_server_dict(config.get("shared_servers", {}))
    return masked


def _mask_server_dict(
    servers: dict[str, Any],
) -> dict[str, Any]:
    """Mask env and header secrets in a servers dict."""
    masked = {}
    for name, srv in servers.items():
        masked_srv = dict(srv)
        if "env" in masked_srv and isinstance(masked_srv["env"], dict):
            masked_srv["env"] = {
                k: (MCP_MASKED_SECRET if v else "")
                for k, v in masked_srv["env"].items()
            }
        if "headers" in masked_srv and isinstance(masked_srv["headers"], dict):
            masked_srv["headers"] = {
                k: (MCP_MASKED_SECRET if v else "")
                for k, v in masked_srv["headers"].items()
            }
        masked[name] = masked_srv
    return masked


def _resolve_masked_envs(
    new_servers: dict[str, dict[str, Any]],
    original_servers: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Resolve masked env and header values against original config."""
    resolved = {}
    for name, srv in new_servers.items():
        resolved_srv = dict(srv)
        if "env" in resolved_srv and isinstance(resolved_srv["env"], dict):
            original_env = original_servers.get(name, {}).get("env", {})
            resolved_srv["env"] = {
                k: (original_env.get(k, "") if v == MCP_MASKED_SECRET else v)
                for k, v in resolved_srv["env"].items()
            }
        if "headers" in resolved_srv and isinstance(resolved_srv["headers"], dict):
            original_headers = original_servers.get(name, {}).get("headers", {})
            resolved_srv["headers"] = {
                k: (original_headers.get(k, "") if v == MCP_MASKED_SECRET else v)
                for k, v in resolved_srv["headers"].items()
            }
        resolved[name] = resolved_srv
    return resolved


@router.get("/admin/api/mcp/config")
async def get_mcp_config(request: Request):
    require_loopback_admin(request)
    config, _ = load_mcp_config()
    # Serialize to dict for masking
    config_dict = {
        "router_socket": config.router_socket,
        "router_pidfile": config.router_pidfile,
        "router_log": config.router_log,
        "health_timeout_s": config.health_timeout_s,
        "servers": {
            name: srv.model_dump(exclude={"name"})
            for name, srv in config.servers.items()
        },
        "shared_servers": {
            name: srv.model_dump(exclude={"name"})
            for name, srv in config.shared_servers.items()
        },
    }
    return _mask_mcp_config(config_dict)


@router.post("/admin/api/mcp/config/validate")
async def validate_mcp_config_route(payload: McpConfigPayload, request: Request):
    require_loopback_admin(request)
    config, _ = load_mcp_config()
    original_servers = {
        name: srv.model_dump(exclude={"name"}) for name, srv in config.servers.items()
    }
    original_shared = {
        name: srv.model_dump(exclude={"name"})
        for name, srv in config.shared_servers.items()
    }
    resolved = _resolve_masked_envs(payload.servers, original_servers)
    resolved_shared = _resolve_masked_envs(payload.shared_servers, original_shared)
    from .mcp_config import validate_mcp_config as validate_fn

    all_servers = {**resolved, **resolved_shared}
    errors = validate_fn(all_servers)
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/admin/api/mcp/config/apply")
async def apply_mcp_config(payload: McpConfigPayload, request: Request):
    require_loopback_admin(request)
    config, _ = load_mcp_config()
    original_servers = {
        name: srv.model_dump(exclude={"name"}) for name, srv in config.servers.items()
    }
    original_shared = {
        name: srv.model_dump(exclude={"name"})
        for name, srv in config.shared_servers.items()
    }
    resolved = _resolve_masked_envs(payload.servers, original_servers)
    resolved_shared = _resolve_masked_envs(payload.shared_servers, original_shared)
    result = write_mcp_config(
        router_socket=payload.router_socket,
        router_log=payload.router_log,
        router_pidfile=payload.router_pidfile,
        health_timeout_s=payload.health_timeout_s,
        servers=resolved,
        shared_servers=resolved_shared,
    )
    return result.model_dump()


@router.get("/admin/api/mcp/status")
async def get_mcp_status(request: Request):
    require_loopback_admin(request)
    config, _ = load_mcp_config()
    return await get_router_status(config.router_socket)


# ---------------------------------------------------------------------------
# MCP SFTP shared config routes
# ---------------------------------------------------------------------------


class SftpConfigPayload(BaseModel):
    """SFTP config update submitted by the admin UI."""

    host: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: str = "password"
    password: str = ""
    private_key: str = ""
    remote_file_path: str = ""
    enabled: bool = False


def _sftp_config_from_settings() -> SftpConfig:
    """Build an SftpConfig from the current cached settings (env)."""
    settings = get_cached_settings()
    auth_method = cast(Literal["password", "key"], settings.sftp_auth_method)
    return SftpConfig(
        host=settings.sftp_host,
        port=settings.sftp_port,
        username=settings.sftp_username,
        auth_method=auth_method,
        password=settings.sftp_password,
        private_key=settings.sftp_private_key,
        remote_file_path=settings.sftp_remote_file_path,
        enabled=settings.sftp_enabled,
    )


@router.get("/admin/api/mcp/sftp-config")
async def get_sftp_config(request: Request):
    require_loopback_admin(request)
    settings = get_cached_settings()
    data: dict[str, Any] = {
        "host": settings.sftp_host,
        "port": settings.sftp_port,
        "username": settings.sftp_username,
        "auth_method": settings.sftp_auth_method,
        "password": MCP_MASKED_SECRET if settings.sftp_password else "",
        "private_key": MCP_MASKED_SECRET if settings.sftp_private_key else "",
        "remote_file_path": settings.sftp_remote_file_path,
        "enabled": settings.sftp_enabled,
    }
    return {"sftp": data}


@router.post("/admin/api/mcp/sftp-config/validate")
async def validate_sftp_config(payload: SftpConfigPayload, request: Request):
    require_loopback_admin(request)
    errors: list[str] = []
    if not payload.host.strip():
        errors.append("Host is required")
    if not payload.username.strip():
        errors.append("Username is required")
    if payload.auth_method == "key" and not payload.private_key.strip():
        errors.append("Private key is required")
    if not payload.remote_file_path.strip():
        errors.append("Remote file path is required")
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/admin/api/mcp/sftp-config/apply")
async def apply_sftp_config(payload: SftpConfigPayload, request: Request):
    require_loopback_admin(request)
    updates: dict[str, Any] = {
        "FCC_SFTP_HOST": payload.host,
        "FCC_SFTP_PORT": str(payload.port),
        "FCC_SFTP_USERNAME": payload.username,
        "FCC_SFTP_AUTH_METHOD": payload.auth_method,
        "FCC_SFTP_PASSWORD": payload.password,
        "FCC_SFTP_PRIVATE_KEY": payload.private_key,
        "FCC_SFTP_REMOTE_FILE_PATH": payload.remote_file_path,
        "FCC_SFTP_ENABLED": "true" if payload.enabled else "false",
    }
    result = write_managed_env(updates)
    get_cached_settings.cache_clear()
    return result


@router.post("/admin/api/mcp/sftp-fetch")
async def sftp_fetch(request: Request):
    """Connect to the remote SFTP server and fetch the shared MCP config."""
    require_loopback_admin(request)
    sftp_config = _sftp_config_from_settings()
    if not sftp_config.enabled:
        return {"ok": False, "error": "SFTP is not configured or not enabled"}
    if not sftp_config.host or not sftp_config.remote_file_path:
        return {
            "ok": False,
            "error": "SFTP host and remote file path must be configured",
        }
    return sftp_fetch_remote_config(sftp_config)


class SftpImportPayload(BaseModel):
    """Import mode for remote MCP config."""

    mode: str = Field(default="merge", description="'merge' or 'replace'")


@router.post("/admin/api/mcp/sftp-import")
async def sftp_import(payload: SftpImportPayload, request: Request):
    """Fetch remote config and import into shared_servers (merge or replace)."""
    require_loopback_admin(request)
    if payload.mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="Mode must be 'merge' or 'replace'")

    config, _ = load_mcp_config()
    sftp_config = _sftp_config_from_settings()
    if not sftp_config.enabled:
        return {"ok": False, "error": "SFTP is not configured or not enabled"}
    if not sftp_config.host or not sftp_config.remote_file_path:
        return {
            "ok": False,
            "error": "SFTP host and remote file path must be configured",
        }

    fetch_result = sftp_fetch_remote_config(sftp_config)
    if not fetch_result["ok"]:
        return fetch_result

    remote_data = fetch_result["config"]
    errors = validate_remote_mcp_config(remote_data)
    if errors:
        return {
            "ok": False,
            "error": "Remote config validation failed",
            "errors": errors,
        }

    remote_servers = remote_data["servers"]
    shared_servers: dict[str, dict[str, Any]] = {}
    if payload.mode == "merge":
        # Preserve existing shared servers
        shared_servers = {
            name: srv.model_dump(exclude={"name"})
            for name, srv in config.shared_servers.items()
        }
        # Add remote servers that don't conflict
        for name, srv in remote_servers.items():
            if name not in shared_servers:
                shared_servers[name] = srv
    else:
        # Replace: use remote servers only
        shared_servers = remote_servers

    local_servers = {
        name: srv.model_dump(exclude={"name"}) for name, srv in config.servers.items()
    }
    result = write_mcp_config(
        router_socket=config.router_socket,
        router_log=config.router_log,
        router_pidfile=config.router_pidfile,
        health_timeout_s=config.health_timeout_s,
        servers=local_servers,
        shared_servers=shared_servers,
    )
    result_data = result.model_dump()
    result_data["ok"] = result.applied
    result_data["imported_count"] = len(shared_servers)
    return result_data
