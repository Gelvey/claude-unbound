from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api.admin_config import MASKED_SECRET
from api.admin_urls import local_admin_url
from api.app import create_app
from config.settings import Settings


def _local_client(app):
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient bound to the local admin address."""
    app = create_app(lifespan_enabled=False)
    return _local_client(app)


def _set_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def _clear_process_config(monkeypatch) -> None:
    for key in (
        "MODEL",
        "NVIDIA_NIM_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "FCC_ENV_FILE",
        "HOST",
        "PORT",
        "LOG_FILE",
        "ZAI_BASE_URL",
        "CLAUDE_WORKSPACE",
        "CLAUDE_CLI_BIN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_admin_page_is_loopback_only(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    app = create_app(lifespan_enabled=False)

    assert _local_client(app).get("/admin").status_code == 200
    remote_client = TestClient(app, client=("203.0.113.10", 50000))
    assert remote_client.get("/admin").status_code == 403


def test_admin_page_no_longer_renders_generated_env_panel(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin")

    assert response.status_code == 200
    assert "Generated Env" not in response.text
    assert "envPreview" not in response.text


def test_admin_page_no_longer_renders_global_status_header(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin")

    assert response.status_code == 200
    assert "Local Admin" not in response.text
    assert "serverStatus" not in response.text
    assert "modelBadge" not in response.text


def test_admin_static_no_longer_fetches_global_status_header():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")

    assert 'api("/admin/api/status")' not in script
    assert "updateHeader" not in script
    assert '"Running"' not in script
    assert "serverStatus" not in script
    assert "modelBadge" not in script


def test_admin_static_hides_managed_source_label():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")

    assert 'managed_env: "",' in script
    assert "hasOwnProperty.call(labels, source)" in script
    assert 'parts.push("locked")' in script
    assert "sourceEl.textContent = source" in script


def test_admin_static_defines_openrouter_policy_view():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")
    html = Path("api/admin_static/index.html").read_text(encoding="utf-8")

    assert 'id: "openrouter_policy"' in script
    assert 'containerId: "openrouterPolicySections"' in script
    assert 'data-view="openrouter_policy"' in html
    assert 'id="openrouterPolicySections"' in html


def test_admin_static_defines_cloudflare_view():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")
    html = Path("api/admin_static/index.html").read_text(encoding="utf-8")

    assert 'id: "cloudflare"' in script
    assert 'containerId: "cloudflareSections"' in script
    assert 'data-view="cloudflare"' in html
    assert 'id="cloudflareSections"' in html


def test_admin_static_defines_mcp_view():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")
    html = Path("api/admin_static/index.html").read_text(encoding="utf-8")

    assert 'id: "mcp"' in script
    assert 'containerId: "mcpSections"' in script
    assert 'data-view="mcp"' in html
    assert 'id="mcpSections"' in html


def test_admin_static_defines_graphify_view():
    script = Path("api/admin_static/admin.js").read_text(encoding="utf-8")
    html = Path("api/admin_static/index.html").read_text(encoding="utf-8")

    assert 'id: "graphify"' in script
    assert 'containerId: "graphifySections"' in script
    assert 'data-view="graphify"' in html
    assert 'id="graphifySections"' in html
    assert "function loadGraphifyView" in script
    assert "function renderGraphifyView" in script


def test_admin_static_serves_favicon_svg(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/assets/favicon.svg")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers.get("content-type", "")
    assert "<svg" in response.text


def test_admin_page_links_to_favicon_svg(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin")

    assert response.status_code == 200
    assert (
        'rel="icon" type="image/svg+xml" href="/admin/assets/favicon.svg"'
        in response.text
    )


def test_admin_config_exposes_openrouter_policy_section(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/config")

    assert response.status_code == 200
    body = response.json()
    section_ids = {section["id"] for section in body["sections"]}
    assert "openrouter_policy" in section_ids
    moved_keys = {
        "OPENROUTER_DATA_COLLECTION",
        "OPENROUTER_FREE_DATA_COLLECTION",
        "OPENROUTER_FREE_MODEL_IDS",
    }
    sections_per_moved_key = {
        field["key"]: field["section"]
        for field in body["fields"]
        if field["key"] in moved_keys
    }
    assert set(sections_per_moved_key) == moved_keys
    assert set(sections_per_moved_key.values()) == {"openrouter_policy"}
    # OPENROUTER_PROXY is an advanced field that wasn't moved; it stays under providers.
    proxy_field = next(
        field for field in body["fields"] if field["key"] == "OPENROUTER_PROXY"
    )
    assert proxy_field["section"] == "providers"


def test_admin_config_exposes_permissions_section(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/config")

    assert response.status_code == 200
    body = response.json()
    section_ids = {section["id"] for section in body["sections"]}
    assert "permissions" in section_ids
    permission_keys = {
        "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
        "CODEX_DANGEROUSLY_BYPASS_APPROVALS",
    }
    sections_per_key = {
        field["key"]: field["section"]
        for field in body["fields"]
        if field["key"] in permission_keys
    }
    assert set(sections_per_key) == permission_keys
    assert set(sections_per_key.values()) == {"permissions"}


def test_admin_env_preview_groups_openrouter_policy_keys(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/validate",
        json={
            "values": {
                "OPENROUTER_DATA_COLLECTION": "deny",
                "OPENROUTER_FREE_DATA_COLLECTION": "allow",
                "OPENROUTER_FREE_MODEL_IDS": "deepseek/deepseek-chat:free",
            }
        },
    )

    assert response.status_code == 200
    preview = response.json()["env_preview"]
    policy_index = preview.index("# OpenRouter Policy")
    providers_index = preview.index("# Providers")
    assert providers_index < policy_index
    for key in (
        "OPENROUTER_DATA_COLLECTION",
        "OPENROUTER_FREE_DATA_COLLECTION",
        "OPENROUTER_FREE_MODEL_IDS",
    ):
        assert f"{key}=" in preview
        assert preview.index(f"{key}=") > policy_index


def test_admin_config_masks_secrets_and_exposes_manifest(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/config")

    assert response.status_code == 200
    body = response.json()
    keys = {field["key"] for field in body["fields"]}
    assert "ANTHROPIC_AUTH_TOKEN" in keys
    assert "OPENROUTER_API_KEY" in keys
    assert "FIREWORKS_API_KEY" in keys
    assert "GEMINI_API_KEY" in keys
    assert "GROQ_API_KEY" in keys
    assert "CEREBRAS_API_KEY" in keys
    assert "ZAI_BASE_URL" not in keys
    assert "CLAUDE_WORKSPACE" not in keys
    assert "CLAUDE_CLI_BIN" not in keys
    assert "LOG_FILE" not in keys
    auth_field = next(
        field for field in body["fields"] if field["key"] == "ANTHROPIC_AUTH_TOKEN"
    )
    assert auth_field["secret"] is True
    assert auth_field["value"] == MASKED_SECRET
    assert auth_field["source"] == "template"


def test_admin_config_preserves_managed_env_source_contract(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    env_file = tmp_path / ".fcc" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("MODEL=open_router/managed-model\n", encoding="utf-8")
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).get("/admin/api/config")

    assert response.status_code == 200
    body = response.json()
    model_field = next(field for field in body["fields"] if field["key"] == "MODEL")
    assert model_field["source"] == "managed_env"
    assert model_field["locked"] is False


def test_admin_validate_rejects_bad_model_shape(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/validate",
        json={"values": {"MODEL": "missing-provider-prefix"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("provider type" in error for error in body["errors"])


def test_admin_apply_writes_complete_managed_env_and_masks_preview(
    monkeypatch, tmp_path
):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={
            "values": {
                "MODEL": "open_router/test-model",
                "OPENROUTER_API_KEY": "router-secret",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert "OPENROUTER_API_KEY=********" in body["env_preview"]
    env_file = tmp_path / ".fcc" / ".env"
    text = env_file.read_text("utf-8")
    assert "MODEL=open_router/test-model" in text
    assert "OPENROUTER_API_KEY=router-secret" in text
    assert "ANTHROPIC_AUTH_TOKEN=" in text
    assert body["restart"] == {
        "required": False,
        "automatic": False,
        "admin_url": None,
        "fields": [],
    }


def test_admin_apply_writes_fireworks_key_and_masks_preview(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={
            "values": {
                "MODEL": "fireworks/test-model",
                "FIREWORKS_API_KEY": "fw-secret",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert "FIREWORKS_API_KEY=********" in body["env_preview"]
    env_file = tmp_path / ".fcc" / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "MODEL=fireworks/test-model" in text
    assert "FIREWORKS_API_KEY=fw-secret" in text


def test_admin_apply_writes_gemini_key_and_masks_preview(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={
            "values": {
                "MODEL": "gemini/models/gemini-3.1-flash-lite",
                "GEMINI_API_KEY": "gm-secret",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert "GEMINI_API_KEY=********" in body["env_preview"]
    env_file = tmp_path / ".fcc" / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "MODEL=gemini/models/gemini-3.1-flash-lite" in text
    assert "GEMINI_API_KEY=gm-secret" in text


def test_admin_apply_writes_groq_key_and_masks_preview(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={
            "values": {
                "MODEL": "groq/llama-3.3-70b-versatile",
                "GROQ_API_KEY": "gq-secret",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert "GROQ_API_KEY=********" in body["env_preview"]
    env_file = tmp_path / ".fcc" / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "MODEL=groq/llama-3.3-70b-versatile" in text
    assert "GROQ_API_KEY=gq-secret" in text


def test_admin_apply_writes_cerebras_key_and_masks_preview(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={
            "values": {
                "MODEL": "cerebras/llama3.1-8b",
                "CEREBRAS_API_KEY": "cb-secret",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert "CEREBRAS_API_KEY=********" in body["env_preview"]
    env_file = tmp_path / ".fcc" / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "MODEL=cerebras/llama3.1-8b" in text
    assert "CEREBRAS_API_KEY=cb-secret" in text


def test_admin_apply_preserves_hidden_diagnostics_and_smoke_values(
    monkeypatch, tmp_path
):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    env_file = tmp_path / ".fcc" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "\n".join(
            [
                "MODEL=nvidia_nim/old-model",
                "LOG_RAW_API_PAYLOADS=true",
                "FCC_SMOKE_MODEL_ZAI=zai/smoke-model",
                "",
            ]
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"MODEL": "open_router/test-model"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    text = env_file.read_text("utf-8")
    assert "MODEL=open_router/test-model" in text
    assert "LOG_RAW_API_PAYLOADS=true" in text
    assert "FCC_SMOKE_MODEL_ZAI=zai/smoke-model" in text


def test_admin_apply_omits_stale_zai_base_url(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    env_file = tmp_path / ".fcc" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "\n".join(
            [
                "MODEL=zai/glm-5.1",
                "ZAI_API_KEY=zai-secret",
                "ZAI_BASE_URL=https://custom.zai.invalid/v1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"MODEL": "zai/glm-5.1"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    text = env_file.read_text("utf-8")
    assert "ZAI_API_KEY=zai-secret" in text
    assert "ZAI_BASE_URL" not in text


def test_admin_apply_omits_stale_fixed_claude_runtime_settings(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    env_file = tmp_path / ".fcc" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "\n".join(
            [
                "MODEL=open_router/test-model",
                "CLAUDE_WORKSPACE=C:/custom/workspace",
                "CLAUDE_CLI_BIN=claude-custom",
                "",
            ]
        ),
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"MODEL": "open_router/test-model"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    text = env_file.read_text("utf-8")
    assert "MODEL=open_router/test-model" in text
    assert "CLAUDE_WORKSPACE" not in text
    assert "CLAUDE_CLI_BIN" not in text


def test_admin_apply_restart_required_reports_automatic_restart(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)
    callbacks: list[str] = []

    async def restart_callback() -> None:
        callbacks.append("restart")

    app.state.admin_restart_callback = restart_callback

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"PORT": "9090"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["pending_fields"] == ["PORT"]
    assert body["restart"] == {
        "required": True,
        "automatic": True,
        "admin_url": "http://127.0.0.1:9090/admin",
        "fields": ["PORT"],
    }
    assert callbacks == ["restart"]


def test_admin_apply_restart_required_reports_manual_fallback(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"PORT": "9091"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["pending_fields"] == ["PORT"]
    assert body["restart"] == {
        "required": True,
        "automatic": False,
        "admin_url": None,
        "fields": ["PORT"],
    }


def test_admin_process_env_values_are_locked_and_not_written(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    monkeypatch.setenv("MODEL", "open_router/process-model")
    app = create_app(lifespan_enabled=False)

    config = _local_client(app).get("/admin/api/config").json()
    model_field = next(field for field in config["fields"] if field["key"] == "MODEL")
    assert model_field["locked"] is True
    assert model_field["source"] == "process"

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {"MODEL": "deepseek/managed-model"}},
    )

    assert response.status_code == 200
    env_file = tmp_path / ".fcc" / ".env"
    assert "deepseek/managed-model" not in env_file.read_text("utf-8")


def test_admin_first_apply_migrates_repo_env(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "MODEL=deepseek/deepseek-chat\nDEEPSEEK_API_KEY=deepseek-secret\n",
        encoding="utf-8",
    )
    app = create_app(lifespan_enabled=False)

    config = _local_client(app).get("/admin/api/config").json()
    model_field = next(field for field in config["fields"] if field["key"] == "MODEL")
    assert model_field["value"] == "deepseek/deepseek-chat"
    assert model_field["source"] == "repo_env"

    response = _local_client(app).post(
        "/admin/api/config/apply",
        json={"values": {}},
    )

    assert response.status_code == 200
    managed_text = (tmp_path / ".fcc" / ".env").read_text("utf-8")
    assert "MODEL=deepseek/deepseek-chat" in managed_text
    assert "DEEPSEEK_API_KEY=deepseek-secret" in managed_text


def test_admin_local_provider_status_reports_reachable(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    app = create_app(lifespan_enabled=False)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str):
            return httpx.Response(200, json={"data": []})

    with patch("api.admin_routes.httpx.AsyncClient", FakeAsyncClient):
        response = _local_client(app).get("/admin/api/providers/local-status")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert {provider["status"] for provider in providers} == {"reachable"}


def test_admin_launch_url_uses_loopback_for_wildcard_host():
    settings = Settings.model_construct(host="0.0.0.0", port=8082)

    assert local_admin_url(settings) == "http://127.0.0.1:8082/admin"


def test_admin_test_provider_returns_http_error_details(monkeypatch, tmp_path):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_AI_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDFLARE_AI_ACCOUNT_ID", "test-account")
    app = create_app(lifespan_enabled=False)

    error_response = httpx.Response(
        status_code=401,
        json={
            "success": False,
            "errors": [{"code": 10000, "message": "Authentication error"}],
        },
        request=httpx.Request("GET", "https://api.cloudflare.com/"),
    )
    http_error = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=httpx.Request("GET", "https://api.cloudflare.com/"),
        response=error_response,
    )

    async def mock_list_model_infos():
        raise http_error

    with patch("providers.registry.ProviderRegistry.get") as mock_get:
        mock_provider = MagicMock()
        mock_provider.list_model_infos = mock_list_model_infos
        mock_get.return_value = mock_provider
        response = _local_client(app).post(
            "/admin/api/providers/cloudflare_ai/test",
            json={},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_type"] == "HTTPStatusError"
    assert body["status_code"] == 401
    assert body["error_message"] == "Authentication error"


def test_admin_test_provider_returns_generic_error_for_non_http_exception(
    monkeypatch, tmp_path
):
    _set_home(monkeypatch, tmp_path)
    _clear_process_config(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_AI_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDFLARE_AI_ACCOUNT_ID", "test-account")
    app = create_app(lifespan_enabled=False)

    with patch("providers.registry.ProviderRegistry.get") as mock_get:
        mock_provider = MagicMock()
        mock_provider.list_model_infos = AsyncMock(
            side_effect=ConnectionError("connection refused")
        )
        mock_get.return_value = mock_provider
        response = _local_client(app).post(
            "/admin/api/providers/cloudflare_ai/test",
            json={},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_type"] == "ConnectionError"
    assert body["error_message"] == "connection refused"
    assert "status_code" not in body


class TestWriteClaudePermissionsSetting:
    """POST /admin/settings/claude_dangerously_skip_permissions writes ~/.claude/settings.json."""

    ENDPOINT = "/admin/settings/claude_dangerously_skip_permissions"

    @staticmethod
    def test_enable_permissions(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text('{"permissions": {}}')

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        written = json.loads(settings_file.read_text())
        assert written["permissions"] == {"defaultMode": "bypassPermissions"}

    @staticmethod
    def test_disable_permissions(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            '{"permissions": {"defaultMode": "bypassPermissions"}}'
        )

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        written = json.loads(settings_file.read_text())
        assert written["permissions"] == {}

    @staticmethod
    def test_creates_settings_file_and_dir_if_missing(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        written = json.loads(settings_file.read_text())
        assert written["permissions"] == {"defaultMode": "bypassPermissions"}

    @staticmethod
    def test_preserves_existing_settings_content(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Read", "Write"]},
                    "env": {"FOO": "bar"},
                    "model": "claude-sonnet-4-20250514",
                }
            )
        )

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": True},
        )
        assert resp.status_code == 200

        written = json.loads(settings_file.read_text())
        assert written["permissions"]["allow"] == ["Read", "Write"]
        assert written["permissions"]["defaultMode"] == "bypassPermissions"
        assert written["env"] == {"FOO": "bar"}
        assert written["model"] == "claude-sonnet-4-20250514"

    @staticmethod
    def test_creates_permissions_section_if_missing(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text('{"env": {"FOO": "bar"}}')

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": True},
        )
        assert resp.status_code == 200

        written = json.loads(settings_file.read_text())
        assert written["permissions"] == {"defaultMode": "bypassPermissions"}
        assert written["env"] == {"FOO": "bar"}

    @staticmethod
    def test_invalid_value_returns_422(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": "not-a-bool"},
        )
        assert resp.status_code == 422

    @staticmethod
    def test_settings_dir_creation_failure_returns_500(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text("invalid json content {{{")

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.post(
            "/admin/settings/claude_dangerously_skip_permissions",
            json={"value": True},
        )
        assert resp.status_code == 500
        data = resp.json()
        assert "detail" in data


class TestReadClaudePermissionsSetting:
    """GET /admin/settings/claude_dangerously_skip_permissions reads ~/.claude/settings.json."""

    ENDPOINT = "/admin/settings/claude_dangerously_skip_permissions"

    @staticmethod
    def test_returns_true_when_enabled(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            '{"permissions": {"defaultMode": "bypassPermissions"}}'
        )

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is True

    @staticmethod
    def test_returns_false_when_disabled(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text('{"permissions": {}}')

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is False

    @staticmethod
    def test_returns_false_when_key_missing(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text('{"permissions": {}}')

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is False

    @staticmethod
    def test_returns_false_when_file_missing(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is False

    @staticmethod
    def test_returns_false_when_json_invalid(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text("not valid json")

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is False

    @staticmethod
    def test_returns_false_when_permissions_section_missing(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text('{"env": {"FOO": "bar"}}')

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is False

    @staticmethod
    def test_preserves_allow_deny_rules(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            json.dumps(
                {
                    "permissions": {
                        "defaultMode": "bypassPermissions",
                        "allow": ["Read", "Write", "Bash(git log:*)"],
                        "deny": ["Bash(rm -rf:*)"],
                    }
                }
            )
        )

        monkeypatch.setenv("HOME", str(tmp_path))

        resp = client.get(
            "/admin/settings/claude_dangerously_skip_permissions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value"] is True

        settings_file_after = json.loads(settings_file.read_text())
        assert settings_file_after["permissions"]["allow"] == [
            "Read",
            "Write",
            "Bash(git log:*)",
        ]
        assert settings_file_after["permissions"]["deny"] == ["Bash(rm -rf:*)"]


class TestClaudePermissionsSourceJson:
    """Test that /admin/api/config reflects settings.json state."""

    @staticmethod
    def test_config_reflects_settings_json_enabled(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Config API shows true when settings.json has bypassPermissions."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            '{"permissions": {"defaultMode": "bypassPermissions"}}'
        )

        monkeypatch.setenv("HOME", str(tmp_path))
        app = create_app(lifespan_enabled=False)
        client = _local_client(app)

        resp = client.get("/admin/api/config")
        assert resp.status_code == 200
        body = resp.json()

        # Find the CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS field
        perm_field = next(
            f
            for f in body["fields"]
            if f["key"] == "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"
        )
        assert perm_field["value"] == "true"
        assert perm_field["source"] == "settings_json"

    @staticmethod
    def test_config_reflects_settings_json_disabled(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Config API shows false when settings.json absent."""
        monkeypatch.setenv("HOME", str(tmp_path))
        app = create_app(lifespan_enabled=False)
        client = _local_client(app)

        resp = client.get("/admin/api/config")
        assert resp.status_code == 200
        body = resp.json()

        perm_field = next(
            f
            for f in body["fields"]
            if f["key"] == "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"
        )
        assert perm_field["value"] == "false"
        assert perm_field["source"] == "settings_json"

    @staticmethod
    def test_apply_writes_settings_json_when_enabled(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Applying toggle writes bypassPermissions to settings.json."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text("{}")

        monkeypatch.setenv("HOME", str(tmp_path))
        app = create_app(lifespan_enabled=False)
        client = _local_client(app)

        resp = client.post(
            "/admin/api/config/apply",
            json={
                "values": {
                    "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS": "true",
                }
            },
        )
        assert resp.status_code == 200

        written = json.loads(settings_file.read_text())
        assert written["permissions"]["defaultMode"] == "bypassPermissions"

    @staticmethod
    def test_apply_removes_settings_json_when_disabled(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Applying toggle removes bypassPermissions from settings.json."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(
            '{"permissions": {"defaultMode": "bypassPermissions"}}'
        )

        monkeypatch.setenv("HOME", str(tmp_path))
        app = create_app(lifespan_enabled=False)
        client = _local_client(app)

        resp = client.post(
            "/admin/api/config/apply",
            json={
                "values": {
                    "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS": "false",
                }
            },
        )
        assert resp.status_code == 200

        written = json.loads(settings_file.read_text())
        assert written["permissions"] == {}

    @staticmethod
    def test_apply_does_not_write_permission_key_to_managed_env(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Env file does not contain CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS."""
        _set_home(monkeypatch, tmp_path)
        _clear_process_config(monkeypatch)

        app = create_app(lifespan_enabled=False)
        client = _local_client(app)

        resp = client.post(
            "/admin/api/config/apply",
            json={
                "values": {
                    "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS": "true",
                }
            },
        )
        assert resp.status_code == 200

        env_file = tmp_path / ".fcc" / ".env"
        if env_file.exists():
            content = env_file.read_text()
            assert "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS" not in content
