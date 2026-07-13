"""Local admin UI routes and APIs."""

from __future__ import annotations

import base64
import inspect
import ipaddress
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.graphify import (
    GraphifyManager,
    add_or_update_project,
    load_project_registry,
    remove_project,
    save_project_registry,
)
from api.graphify.graphs import read_graph_summary
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


@router.get("/admin/api/modules/tabs")
async def admin_module_tabs(request: Request):
    """Return the list of custom admin tabs contributed by loaded modules."""
    require_loopback_admin(request)
    from api.modules.contracts import AdminTabSpec

    raw = getattr(request.app.state, "admin_tabs", []) or []
    tabs: list[dict[str, str | None]] = []
    for tab in raw:
        if isinstance(tab, AdminTabSpec):
            tabs.append(
                {
                    "id": tab.id,
                    "label": tab.label,
                    "title": tab.title,
                    "html": tab.html,
                    "mount_js": tab.mount_js,
                }
            )
        elif isinstance(tab, dict):
            tabs.append(
                {
                    "id": tab.get("id", ""),
                    "label": tab.get("label", ""),
                    "title": tab.get("title", ""),
                    "html": tab.get("html", ""),
                    "mount_js": tab.get("mount_js"),
                }
            )
    return {"tabs": tabs}


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
    # Surface module-registered MCP backends so they show up in the admin UI;
    # user-saved entries still take precedence over module-supplied ones.
    from .mcp_config import merge_module_backends

    module_backends = list(getattr(request.app.state, "mcp_servers", []) or [])
    merged_servers = merge_module_backends(config.servers, module_backends)

    config_dict = {
        "router_socket": config.router_socket,
        "router_pidfile": config.router_pidfile,
        "router_log": config.router_log,
        "health_timeout_s": config.health_timeout_s,
        "servers": {
            name: srv.model_dump(exclude={"name"})
            for name, srv in merged_servers.items()
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


# ---------------------------------------------------------------------------
# Graphify admin routes
# ---------------------------------------------------------------------------


def _get_graphify_manager(request: Request) -> GraphifyManager:
    """Return the shared GraphifyManager singleton (stored on app.state)."""
    manager = getattr(request.app.state, "graphify_manager", None)
    if manager is None:
        settings = get_cached_settings()
        manager = GraphifyManager(settings)
        request.app.state.graphify_manager = manager
    return manager


class GraphifyProjectPayload(BaseModel):
    """Add or update a Graphify project."""

    path: str
    name: str | None = None
    graphify_out: str = "graphify-out"


@router.get("/admin/api/graphify/status")
async def graphify_status(request: Request):
    """Return Graphify status for the admin panel."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    return manager.status()


@router.post("/admin/api/graphify/setup")
async def graphify_setup(request: Request):
    """Verify/install Graphify and return readiness info."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    return await manager.setup(create_venv=True)


@router.post("/admin/api/graphify/start")
async def graphify_start(request: Request):
    """Start the Graphify HTTP MCP server."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    success = await manager.start()
    result: dict[str, Any] = {
        "success": success,
        "status": manager.status(),
    }
    if not success and manager.last_error:
        result["error"] = manager.last_error
    return result


@router.post("/admin/api/graphify/stop")
async def graphify_stop(request: Request):
    """Stop the Graphify HTTP MCP server."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    await manager.stop()
    return {"success": True, "status": manager.status()}


@router.post("/admin/api/graphify/restart")
async def graphify_restart(request: Request):
    """Restart the Graphify HTTP MCP server."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    success = await manager.restart()
    return {
        "success": success,
        "status": manager.status(),
    }


@router.get("/admin/api/graphify/health")
async def graphify_health(request: Request):
    """Probe the Graphify /mcp endpoint."""
    require_loopback_admin(request)
    manager = _get_graphify_manager(request)
    if manager.is_running:
        return await manager.health_check()
    return {"status": "not_running", "error": "Graphify is not running"}


@router.get("/admin/api/graphify/projects")
async def graphify_projects(request: Request):
    """List registered Graphify projects."""
    require_loopback_admin(request)
    registry = load_project_registry()
    return {
        "active_project_path": registry.active_project_path,
        "projects": [project.model_dump() for project in registry.projects],
    }


@router.post("/admin/api/graphify/projects")
async def graphify_add_project(payload: GraphifyProjectPayload, request: Request):
    """Add or update a Graphify project."""
    require_loopback_admin(request)
    registry = load_project_registry()
    project = add_or_update_project(
        registry,
        path=payload.path,
        name=payload.name,
        graphify_out=payload.graphify_out,
    )
    save_project_registry(registry)
    return {"success": True, "project": project.model_dump()}


def _decode_project_path(path_b64: str) -> str:
    """Decode a base64 project path from a URL segment.

    Accepts URL-safe base64 with or without padding so the web UI can strip
    trailing ``=`` characters for cleaner URLs.
    """
    padding_needed = (4 - len(path_b64) % 4) % 4
    padded = path_b64 + ("=" * padding_needed)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


@router.delete("/admin/api/graphify/projects/{path_b64}")
async def graphify_remove_project(path_b64: str, request: Request):
    """Remove a Graphify project by base64-encoded path."""
    require_loopback_admin(request)
    path = _decode_project_path(path_b64)
    registry = load_project_registry()
    removed = remove_project(registry, path)
    save_project_registry(registry)
    return {"success": removed}


@router.post("/admin/api/graphify/projects/{path_b64}/index")
async def graphify_index_project(path_b64: str, request: Request):
    """Run graphify extract/update for a project in the background."""
    require_loopback_admin(request)
    path = _decode_project_path(path_b64)
    registry = load_project_registry()
    matches = [p for p in registry.projects if p.path == path]
    if not matches:
        raise HTTPException(status_code=404, detail="Project not found")
    manager = _get_graphify_manager(request)
    return await manager.start_index_project(matches[0])


@router.get("/admin/api/graphify/projects/{path_b64}/index/status")
async def graphify_index_project_status(path_b64: str, request: Request):
    """Return live status for an in-progress project index task."""
    require_loopback_admin(request)
    path = _decode_project_path(path_b64)
    registry = load_project_registry()
    project = next((p for p in registry.projects if p.path == path), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    manager = _get_graphify_manager(request)
    task_status = manager.get_index_task_status(path)
    result: dict[str, Any] = {
        "path": path,
        "status": project.status,
        "last_indexed": project.last_indexed.isoformat()
        if project.last_indexed
        else None,
        "error_message": project.error_message,
    }
    if task_status is not None:
        result["task"] = task_status
    # Include queue position so the UI can show "Queued (2 of 5)".
    if project.status == "queued":
        for i, item in enumerate(manager.index_queue_snapshot):
            if item["path"] == path:
                result["queue_position"] = i + 1
                break
    result["current_indexing"] = manager._index_current
    return result


@router.get("/admin/api/graphify/projects/{path_b64}/graph")
async def graphify_project_graph(path_b64: str, request: Request):
    """Return a compact summary of a project's knowledge graph.

    ``{"present": false, "reason": "not_indexed"}`` when the graph has not been
    built yet. 404 when the project is unknown. The full graph.json (can be many
    MB) is never returned — only counts.
    """
    require_loopback_admin(request)
    path = _decode_project_path(path_b64)
    registry = load_project_registry()
    project = next((p for p in registry.projects if p.path == path), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return read_graph_summary(project)


# ---------------------------------------------------------------------------
# Composio MCP integration helpers
# ---------------------------------------------------------------------------

COMPOSIO_DEFAULT_URL = "https://connect.composio.dev/mcp"
COMPOSIO_DEFAULT_PORT = 7110
COMPOSIO_API_KEY_HEADER = "x-consumer-api-key"
COMPOSIO_TEST_TIMEOUT_S = 15.0


class ComposioTestPayload(BaseModel):
    """Optional API key override for testing Composio connectivity."""

    api_key: str = ""


class ComposioSetupPayload(BaseModel):
    """Composio quick-setup payload."""

    api_key: str
    port: int = Field(default=COMPOSIO_DEFAULT_PORT, ge=1, le=65535)


def _lookup_composio_api_key(headers: dict[str, str]) -> str:
    """Return the configured Composio API key, matching the header by HTTP-case.

    HTTP header names are case-insensitive, but Python dicts are not. Allow
    users to write ``X-Consumer-Api-Key`` and have it recognized.
    """
    target = COMPOSIO_API_KEY_HEADER.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return ""


def _build_composio_entry(
    api_key: str,
    port: int = COMPOSIO_DEFAULT_PORT,
    existing_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Construct a ``composio`` MCP backend config entry.

    Preserves any custom headers already present (other than the API key
    itself), so updating the key never wipes user customisations.
    """
    headers = {
        k: v
        for k, v in (existing_headers or {}).items()
        if k.lower() != COMPOSIO_API_KEY_HEADER.lower()
    }
    headers[COMPOSIO_API_KEY_HEADER] = api_key
    return {
        "type": "http",
        "url": COMPOSIO_DEFAULT_URL,
        "port": port,
        "headers": headers,
    }


def _sanitize_composio_error(api_key: str, message: str) -> str:
    """Redact the API key from a Composio error message before returning it.

    Prevents leaking the provisioned key if an upstream library echoes it
    back in its exception text (e.g. via URL-encoded HTTP headers).
    """
    if not api_key or not message:
        return message
    redacted = message.replace(api_key, "[REDACTED]")
    if redacted == message and api_key in message:
        # Substring variant (e.g. URL-encoded) - redact each segment.
        return message.replace(api_key, "[REDACTED]")
    return redacted


async def _test_composio_connection(api_key: str) -> dict:
    """Test connectivity to Composio's MCP endpoint.

    Uses the provided API key to connect to Composio via Streamable HTTP,
    calls initialize + list_tools, and returns the tool list.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {COMPOSIO_API_KEY_HEADER: api_key}
    async with (
        streamable_http_client(
            COMPOSIO_DEFAULT_URL,
            http_client=httpx.AsyncClient(
                headers=headers, timeout=COMPOSIO_TEST_TIMEOUT_S
            ),
        ) as (read_stream, write_stream, _get_session_id),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools_result = await session.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        return {
            "ok": True,
            "tool_count": len(tool_names),
            "tool_names": tool_names,
        }


@router.post("/admin/api/mcp/composio/test")
async def composio_test_connection(payload: ComposioTestPayload, request: Request):
    """Test connectivity to Composio's MCP endpoint.

    Uses the provided API key or falls back to the configured ``composio``
    backend's ``x-consumer-api-key`` header. Header lookup is
    case-insensitive.
    """
    require_loopback_admin(request)

    api_key = payload.api_key.strip()
    if not api_key:
        # Fall back to configured composio backend
        config, _ = load_mcp_config()
        composio = config.servers.get("composio")
        if composio is None:
            return {
                "ok": False,
                "error": "No Composio backend configured and no API key provided",
            }
        api_key = _lookup_composio_api_key(composio.headers)
        if not api_key:
            return {"ok": False, "error": "Composio backend has no API key configured"}

    try:
        return await _test_composio_connection(api_key)
    except BaseExceptionGroup as exc:
        # mcp.client.streamable_http uses asyncio.TaskGroup internally, so
        # subprocess failures (network, auth, stream timeout, ...) surface as
        # an ExceptionGroup. PEP 654 keeps such groups outside ``Exception``
        # so callers must opt in; recursively flatten to expose the real
        # cause(s) since groups can nest.
        leaves: list[BaseException] = []
        stack: list[BaseException] = list(exc.exceptions)
        while stack:
            current = stack.pop()
            if isinstance(current, BaseExceptionGroup):
                stack.extend(current.exceptions)
            else:
                leaves.append(current)
        detail = "; ".join(str(leaf) for leaf in leaves)
        return {"ok": False, "error": _sanitize_composio_error(api_key, detail)}
    except Exception as exc:
        return {"ok": False, "error": _sanitize_composio_error(api_key, str(exc))}


@router.post("/admin/api/mcp/composio/setup")
async def composio_setup(payload: ComposioSetupPayload, request: Request):
    """Create or update the ``composio`` MCP backend entry.

    Pre-fills URL, API key header, and port.  Validates and writes config.
    Existing custom headers (other than the API key itself) are preserved
    across updates so user customisations are not wiped.
    """
    require_loopback_admin(request)

    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    config, _ = load_mcp_config()
    servers = {
        name: srv.model_dump(exclude={"name"}) for name, srv in config.servers.items()
    }
    shared_servers = {
        name: srv.model_dump(exclude={"name"})
        for name, srv in config.shared_servers.items()
    }

    existing_headers = servers.get("composio", {}).get("headers") or {}
    servers["composio"] = _build_composio_entry(
        api_key=api_key,
        port=payload.port,
        existing_headers=existing_headers,
    )

    result = write_mcp_config(
        router_socket=config.router_socket,
        router_log=config.router_log,
        router_pidfile=config.router_pidfile,
        health_timeout_s=config.health_timeout_s,
        servers=servers,
        shared_servers=shared_servers,
    )
    return result.model_dump()
