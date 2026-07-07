"""Print live Freebuff status for Claude Code sessions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger

from api.model_router import ModelRouter
from config.paths import server_log_path
from config.settings import Settings
from providers.freebuff.config_generator import read_config_port

_TIMEOUT_SECONDS = 2.0


def main() -> int:
    logger.remove()
    settings = Settings()
    health_result = fetch_freebuff_health(settings)
    model_count = (
        fetch_model_count(health_result.base_url) if health_result.data else None
    )
    print(
        format_freebuff_status(
            settings,
            health=health_result.data,
            base_url=health_result.base_url,
            model_count=model_count,
            latest_route=latest_freebuff_route(server_log_path()),
        )
    )
    return 0


class HealthResult:
    def __init__(self, *, base_url: str, data: dict[str, Any] | None):
        self.base_url = base_url
        self.data = data


def fetch_freebuff_health(settings: Settings) -> HealthResult:
    last_base_url = ""
    for base_url in candidate_freebuff_base_urls(settings):
        last_base_url = base_url
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError, ValueError, TypeError:
            continue
        if isinstance(data, dict):
            return HealthResult(base_url=base_url, data=data)
    return HealthResult(base_url=last_base_url, data=None)


def fetch_model_count(base_url: str) -> int | None:
    if not base_url:
        return None
    try:
        response = httpx.get(f"{base_url}/v1/models", timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError, ValueError, TypeError:
        return None
    models = data.get("data") if isinstance(data, dict) else None
    return len(models) if isinstance(models, list) else None


def candidate_freebuff_base_urls(settings: Settings) -> tuple[str, ...]:
    urls: list[str] = []

    port = read_config_port()
    if port:
        urls.append(f"http://127.0.0.1:{port}")

    configured = strip_openai_version_path(settings.freebuff_base_url)
    if configured:
        urls.append(configured)

    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return tuple(deduped)


def strip_openai_version_path(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    if not url:
        return ""

    parts = urlsplit(url)
    if parts.path.rstrip("/") == "/v1":
        parts = parts._replace(path="")
        return urlunsplit(parts).rstrip("/")
    return url


def format_freebuff_status(
    settings: Settings,
    *,
    health: dict[str, Any] | None,
    base_url: str,
    model_count: int | None,
    latest_route: dict[str, Any] | None,
) -> str:
    lines = ["Freebuff status"]
    lines.append(f"Proxy: {'healthy' if health else 'unreachable'}")
    if base_url:
        lines.append(f"Base URL: {base_url}")
    lines.append("Limit usage: unavailable from Freebuff API")

    routes = freebuff_routes(settings)
    if routes:
        lines.append("")
        lines.append("Configured Freebuff routes:")
        lines.extend(f"  {route}" for route in routes)
        lines.append("Reasoning: max effort requested for Freebuff calls")
    else:
        lines.append("")
        lines.append("Configured Freebuff routes: none")

    if latest_route:
        lines.append("")
        lines.append(
            "Last Freebuff request: "
            f"{latest_route.get('provider_model_ref') or latest_route.get('provider_model')}"
        )
        if latest_route.get("time"):
            lines.append(f"Last request time: {latest_route['time']}")

    if not health:
        lines.append("")
        lines.append("Freebuff proxy is not responding to /healthz.")
        return "\n".join(lines)

    token_states = token_states_from_health(health)
    totals = request_totals(token_states)
    active_sessions = sum(
        1
        for token_state in token_states
        if token_state.get("session_status") in {"active", "ok", "ready"}
    )

    lines.append("")
    lines.append(f"Sessions: {active_sessions}/{len(token_states)} active")
    lines.append(f"Requests this run: {totals['requests']}")
    lines.append(f"Inflight requests: {totals['inflight']}")

    expiry = soonest_session_expiry(token_states)
    if expiry:
        lines.append(f"Nearest session expiry: {expiry}")

    cooldown_count = sum(
        1 for token_state in token_states if token_state.get("cooldown_until")
    )
    if cooldown_count:
        lines.append(f"Cooldown tokens: {cooldown_count}")

    last_error = latest_token_error(token_states)
    if last_error:
        lines.append(f"Last error: {last_error}")

    uptime = format_seconds(health.get("uptime_sec"))
    if uptime:
        lines.append(f"Proxy uptime: {uptime}")
    if model_count is not None:
        lines.append(f"Available models: {model_count}")

    lines.append("")
    lines.append(
        "Note: Claude Code's built-in /usage panel is local session accounting; "
        "FCC cannot replace that panel text."
    )
    return "\n".join(lines)


def freebuff_routes(settings: Settings) -> list[str]:
    router = ModelRouter(settings)
    incoming_models = (
        ("Default", "claude-default"),
        ("Opus", "claude-opus-4-1"),
        ("Sonnet", "claude-sonnet-4-5"),
        ("Haiku", "claude-3-5-haiku-latest"),
    )
    routes: list[str] = []
    for label, incoming_model in incoming_models:
        resolved = router.resolve(incoming_model)
        if resolved.provider_id == "freebuff":
            routes.append(f"{label}: {resolved.provider_model_ref}")
    return routes


def latest_freebuff_route(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 200_000))
            content = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    for line in reversed(content.splitlines()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("event") == "api.route.resolved"
            and item.get("provider_id") == "freebuff"
        ):
            return item
    return None


def token_states_from_health(health: dict[str, Any]) -> list[dict[str, Any]]:
    token_state = health.get("token_state")
    if not isinstance(token_state, list):
        return []
    return [item for item in token_state if isinstance(item, dict)]


def request_totals(token_states: list[dict[str, Any]]) -> dict[str, int]:
    requests = 0
    inflight = 0
    for token_state in token_states:
        runs = token_state.get("runs")
        if not isinstance(runs, list):
            continue
        for run in runs:
            if not isinstance(run, dict):
                continue
            requests += safe_int(run.get("request_count"))
            inflight += safe_int(run.get("inflight"))
    return {"requests": requests, "inflight": inflight}


def soonest_session_expiry(token_states: list[dict[str, Any]]) -> str:
    expiries: list[datetime] = []
    for token_state in token_states:
        raw_expiry = token_state.get("session_expires_at")
        if not isinstance(raw_expiry, str) or not raw_expiry:
            continue
        expiry = parse_datetime(raw_expiry)
        if expiry is not None:
            expiries.append(expiry)

    if not expiries:
        return ""

    expiry = min(expiries)
    remaining = int((expiry - datetime.now(UTC)).total_seconds())
    if remaining <= 0:
        return "expired"
    return f"in {format_seconds(remaining)}"


def latest_token_error(token_states: list[dict[str, Any]]) -> str:
    errors = [
        str(token_state["last_error"])
        for token_state in token_states
        if token_state.get("last_error")
    ]
    return errors[-1] if errors else ""


def parse_datetime(raw_value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_seconds(raw_seconds: Any) -> str:
    seconds = safe_int(raw_seconds)
    if seconds <= 0:
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
