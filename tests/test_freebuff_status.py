import json

from config.settings import Settings
from scripts.freebuff_status import (
    format_freebuff_status,
    freebuff_routes,
    latest_freebuff_route,
)


def test_freebuff_routes_lists_configured_freebuff_tiers() -> None:
    settings = Settings()
    settings.model = "cloudflare_ai/@cf/zai-org/glm-5.2"
    settings.model_haiku = "freebuff/deepseek/deepseek-v4-pro"
    settings.model_sonnet = "cloudflare_ai/@cf/moonshotai/kimi-k2.7-code"
    settings.model_opus = None

    assert freebuff_routes(settings) == ["Haiku: freebuff/deepseek/deepseek-v4-pro"]


def test_format_freebuff_status_includes_health_and_usage_fields() -> None:
    settings = Settings()
    settings.model = "cloudflare_ai/@cf/zai-org/glm-5.2"
    settings.model_haiku = "freebuff/deepseek/deepseek-v4-pro"
    settings.model_sonnet = None
    settings.model_opus = None
    health = {
        "uptime_sec": 3661,
        "token_state": [
            {
                "session_status": "active",
                "runs": [
                    {"request_count": 4, "inflight": 1},
                    {"request_count": 2, "inflight": 0},
                ],
            }
        ],
    }

    text = format_freebuff_status(
        settings,
        health=health,
        base_url="http://127.0.0.1:55825",
        model_count=10,
        latest_route={
            "provider_model_ref": "freebuff/deepseek/deepseek-v4-pro",
            "time": "2026-07-06 04:21:34.707094+10:00",
        },
    )

    assert "Proxy: healthy" in text
    assert "Limit usage: unavailable from Freebuff API" in text
    assert "Haiku: freebuff/deepseek/deepseek-v4-pro" in text
    assert "Requests this run: 6" in text
    assert "Inflight requests: 1" in text
    assert "Proxy uptime: 1h 1m 1s" in text
    assert "Available models: 10" in text


def test_latest_freebuff_route_reads_recent_route_event(tmp_path) -> None:
    log_path = tmp_path / "server.log"
    log_path.write_text(
        "\n".join(
            [
                json.dumps({"event": "api.route.resolved", "provider_id": "groq"}),
                json.dumps(
                    {
                        "event": "api.route.resolved",
                        "provider_id": "freebuff",
                        "provider_model_ref": "freebuff/deepseek/deepseek-v4-pro",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    route = latest_freebuff_route(log_path)

    assert route is not None
    assert route["provider_model_ref"] == "freebuff/deepseek/deepseek-v4-pro"
