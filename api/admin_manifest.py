"""Admin UI configuration manifest: field specs, sections, and lookup indexes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FieldType = Literal[
    "text",
    "secret",
    "number",
    "boolean",
    "tri_boolean",
    "select",
    "textarea",
]
SourceType = Literal[
    "default",
    "template",
    "repo_env",
    "managed_env",
    "explicit_env_file",
    "process",
    "settings_json",
]

MASKED_SECRET = "********"

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


@dataclass(frozen=True, slots=True)
class ConfigSectionSpec:
    """A group of config fields rendered together in the admin UI."""

    section_id: str
    label: str
    description: str
    advanced: bool = False


@dataclass(frozen=True, slots=True)
class ConfigFieldSpec:
    """Typed metadata for one env-backed admin setting."""

    key: str
    label: str
    section_id: str
    field_type: FieldType = "text"
    settings_attr: str | None = None
    default: str = ""
    options: tuple[str, ...] = ()
    model_options: bool = False
    secret: bool = False
    advanced: bool = False
    restart_required: bool = False
    session_sensitive: bool = False
    description: str = ""


SECTIONS: tuple[ConfigSectionSpec, ...] = (
    ConfigSectionSpec(
        "providers",
        "Providers",
        "Provider keys, local endpoints, and proxy settings.",
    ),
    ConfigSectionSpec(
        "cloudflare",
        "Cloudflare Workers AI",
        "Cloudflare Workers AI API token, account ID, and proxy settings.",
    ),
    ConfigSectionSpec(
        "openrouter_policy",
        "OpenRouter Policy",
        "Per-request data_collection policy and free-model allowlist.",
    ),
    ConfigSectionSpec(
        "models",
        "Model Routing",
        "Provider-prefixed models used for Claude model tiers.",
    ),
    ConfigSectionSpec(
        "thinking",
        "Thinking",
        "Global and tier-specific thinking behavior.",
    ),
    ConfigSectionSpec(
        "permissions",
        "Permissions",
        ("Permission bypass settings for managed Claude Code and Codex CLI sessions."),
    ),
    ConfigSectionSpec(
        "runtime",
        "Runtime",
        "Server API token, rate limits, timeouts, and process settings.",
    ),
    ConfigSectionSpec(
        "messaging",
        "Messaging",
        "Discord, Telegram, CLI workspace, and session settings.",
    ),
    ConfigSectionSpec(
        "voice",
        "Voice",
        "Voice note transcription settings.",
    ),
    ConfigSectionSpec(
        "web_tools",
        "Web Tools",
        "Local Anthropic web_search and web_fetch behavior.",
    ),
    ConfigSectionSpec(
        "diagnostics",
        "Diagnostics",
        "Logging and debugging flags.",
        advanced=True,
    ),
    ConfigSectionSpec(
        "smoke",
        "Smoke Tests",
        "Optional live smoke-test model overrides.",
        advanced=True,
    ),
    ConfigSectionSpec(
        "freebuff",
        "Freebuff",
        "Freebuff2API managed proxy to codebuff.com (free models).",
    ),
    ConfigSectionSpec(
        "graphify",
        "Graphify",
        "Graphify knowledge-graph integration for per-project code understanding.",
    ),
    ConfigSectionSpec(
        "mcp_shared",
        "MCP Shared Config (SFTP)",
        "SFTP credentials for fetching shared MCP backends from a remote server.",
        advanced=True,
    ),
)


FIELDS: tuple[ConfigFieldSpec, ...] = (
    ConfigFieldSpec(
        "NVIDIA_NIM_API_KEY",
        "NVIDIA NIM API Key",
        "providers",
        "secret",
        settings_attr="nvidia_nim_api_key",
        secret=True,
        description="Used by NVIDIA NIM chat and optional NIM voice transcription.",
    ),
    ConfigFieldSpec(
        "OPENROUTER_API_KEY",
        "OpenRouter API Key",
        "providers",
        "secret",
        settings_attr="open_router_api_key",
        secret=True,
    ),
    ConfigFieldSpec(
        "MISTRAL_API_KEY",
        "Mistral API Key",
        "providers",
        "secret",
        settings_attr="mistral_api_key",
        secret=True,
        description=(
            "Mistral La Plateforme (api.mistral.ai); Experiment plan is free tier with rate limits."
        ),
    ),
    ConfigFieldSpec(
        "CODESTRAL_API_KEY",
        "Codestral API Key",
        "providers",
        "secret",
        settings_attr="codestral_api_key",
        secret=True,
        description=(
            "Mistral Codestral endpoint (codestral.mistral.ai); distinct from Mistral "
            "La Plateforme ``MISTRAL_API_KEY``. See Mistral docs for coding/FIM domains."
        ),
    ),
    ConfigFieldSpec(
        "DEEPSEEK_API_KEY",
        "DeepSeek API Key",
        "providers",
        "secret",
        settings_attr="deepseek_api_key",
        secret=True,
    ),
    ConfigFieldSpec(
        "KIMI_API_KEY",
        "Kimi API Key",
        "providers",
        "secret",
        settings_attr="kimi_api_key",
        secret=True,
    ),
    ConfigFieldSpec(
        "WAFER_API_KEY",
        "Wafer API Key",
        "providers",
        "secret",
        settings_attr="wafer_api_key",
        secret=True,
    ),
    ConfigFieldSpec(
        "OPENCODE_API_KEY",
        "OpenCode API Key",
        "providers",
        "secret",
        settings_attr="opencode_api_key",
        secret=True,
        description=(
            "OpenCode Zen curated gateway (opencode.ai/zen/v1) and OpenCode Go subscription "
            "gateway (opencode.ai/zen/go/v1); single key from opencode.ai/auth."
        ),
    ),
    ConfigFieldSpec(
        "ZAI_API_KEY",
        "Z.ai API Key",
        "providers",
        "secret",
        settings_attr="zai_api_key",
        secret=True,
        description="Z.ai Coding Plan API key.",
    ),
    ConfigFieldSpec(
        "FIREWORKS_API_KEY",
        "Fireworks API Key",
        "providers",
        "secret",
        settings_attr="fireworks_api_key",
        secret=True,
        description="Fireworks AI inference API key.",
    ),
    ConfigFieldSpec(
        "GEMINI_API_KEY",
        "Gemini API Key",
        "providers",
        "secret",
        settings_attr="gemini_api_key",
        secret=True,
        description=(
            "Google AI Studio Gemini API key (Google AI Studio / Gemini API "
            "[OpenAI-compatible](https://ai.google.dev/gemini-api/docs/openai)); "
            "free tier has per-model rate limits and data may be used for improvement "
            "outside the UK/CH/EEA/EU."
        ),
    ),
    ConfigFieldSpec(
        "VERTEX_AI_PROJECT_ID",
        "Vertex AI Project ID",
        "providers",
        settings_attr="vertex_ai_project_id",
        description=(
            "Google Cloud project ID for Vertex AI. Uses Application Default "
            "Credentials (ADC) instead of an API key — run "
            "`gcloud auth application-default login` to authenticate. "
            "Bills against your Google Cloud $300 free trial credit."
        ),
    ),
    ConfigFieldSpec(
        "VERTEX_AI_LOCATION",
        "Vertex AI Location",
        "providers",
        settings_attr="vertex_ai_location",
        default="global",
        description=(
            "Vertex AI region. 'global' (default) routes to the global endpoint "
            "and is required for Gemini 3.x preview models. Regional endpoints "
            "(e.g. 'us-central1') may have lower latency for GA models."
        ),
    ),
    ConfigFieldSpec(
        "VERTEX_AI_BASE_URL",
        "Vertex AI Base URL Override",
        "providers",
        settings_attr="vertex_ai_base_url",
        advanced=True,
        description=(
            "Optional full URL override for the Vertex AI OpenAI-compat endpoint. "
            "Empty (default) composes the URL from project ID and location."
        ),
    ),
    ConfigFieldSpec(
        "GROQ_API_KEY",
        "Groq API Key",
        "providers",
        "secret",
        settings_attr="groq_api_key",
        secret=True,
        description=(
            "GroqCloud OpenAI-compatible API key ([console.groq.com/keys]"
            "(https://console.groq.com/keys)); see Groq "
            "[OpenAI compatibility docs](https://console.groq.com/docs/openai)."
        ),
    ),
    ConfigFieldSpec(
        "CEREBRAS_API_KEY",
        "Cerebras API Key",
        "providers",
        "secret",
        settings_attr="cerebras_api_key",
        secret=True,
        description=(
            "Cerebras Inference API key (create in [Cloud Console](https://cloud.cerebras.ai)); "
            "see [Quickstart](https://inference-docs.cerebras.ai/quickstart) and "
            "[OpenAI compatibility](https://inference-docs.cerebras.ai/resources/openai)."
        ),
    ),
    ConfigFieldSpec(
        "CLOUDFLARE_AI_API_KEY",
        "Cloudflare Workers AI API Key",
        "cloudflare",
        "secret",
        settings_attr="cloudflare_ai_api_key",
        secret=True,
        description=(
            "Cloudflare Workers AI API token from "
            "[dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens). "
            "Requires ``Workers AI - Read`` and ``Workers AI - Edit`` permissions. "
            "Pair with ``CLOUDFLARE_AI_ACCOUNT_ID`` below. Free tier: "
            "10,000 neurons/day reset at 00:00 UTC."
        ),
    ),
    ConfigFieldSpec(
        "CLOUDFLARE_AI_ACCOUNT_ID",
        "Cloudflare Workers AI Account ID",
        "cloudflare",
        settings_attr="cloudflare_ai_account_id",
        description=(
            "Cloudflare account id used in the upstream URL path "
            "(``/client/v4/accounts/<id>/ai/v1/chat/completions``). Find it in "
            "the Cloudflare dashboard under **Workers AI → Use REST API**, or in "
            "the right sidebar of any dashboard page."
        ),
    ),
    ConfigFieldSpec(
        "LM_STUDIO_BASE_URL",
        "LM Studio Base URL",
        "providers",
        settings_attr="lm_studio_base_url",
        default="http://localhost:1234/v1",
    ),
    ConfigFieldSpec(
        "LLAMACPP_BASE_URL",
        "llama.cpp Base URL",
        "providers",
        settings_attr="llamacpp_base_url",
        default="http://localhost:8080/v1",
    ),
    ConfigFieldSpec(
        "OLLAMA_BASE_URL",
        "Ollama Base URL",
        "providers",
        settings_attr="ollama_base_url",
        default="http://localhost:11434",
    ),
    # ==================== Freebuff2API ====================
    ConfigFieldSpec(
        "FREEBUFF_ENABLED",
        "Enable Freebuff Provider",
        "freebuff",
        "boolean",
        settings_attr="freebuff_enabled",
        default="false",
        description=(
            "Enable the Freebuff2API managed proxy to codebuff.com for free models. "
            "Requires Docker or Go to be installed, and Freebuff credentials at "
            "~/.config/manicode/credentials.json (run 'npm i -g freebuff && freebuff' to login)."
        ),
    ),
    ConfigFieldSpec(
        "FREEBUFF_BASE_URL",
        "Freebuff Base URL",
        "freebuff",
        settings_attr="freebuff_base_url",
        default="http://127.0.0.1:8080",
        description=(
            "Base URL for the Freebuff2API proxy.  Usually set automatically by the "
            "managed subprocess; override only if running Freebuff2API externally."
        ),
    ),
    ConfigFieldSpec(
        "FREEBUFF_CREDENTIALS_PATH",
        "Freebuff Credentials Path",
        "freebuff",
        settings_attr="freebuff_credentials_path",
        default="",
        description=(
            "Path to the Freebuff credentials file.  Leave empty to use the default "
            "~/.config/manicode/credentials.json."
        ),
    ),
    ConfigFieldSpec(
        "FREEBUFF_PROXY",
        "Freebuff Proxy",
        "freebuff",
        "secret",
        settings_attr="freebuff_proxy",
        secret=True,
        advanced=True,
    ),
    # ==================== Graphify ====================
    ConfigFieldSpec(
        "GRAPHIFY_ENABLED",
        "Enable Graphify",
        "graphify",
        "boolean",
        settings_attr="graphify_enabled",
        default="false",
        restart_required=True,
        description=(
            "Start the Graphify MCP server and register it as a Claude Code "
            "MCP server (sibling to the MCP Router in ~/.claude.json, not a "
            "backend inside the router)."
        ),
    ),
    ConfigFieldSpec(
        "GRAPHIFY_SERVER_PORT",
        "Graphify Server Port",
        "graphify",
        "number",
        settings_attr="graphify_server_port",
        default="0",
        advanced=True,
        description=(
            "Port for the local Graphify MCP HTTP server. 0 selects a free "
            "port automatically; a fixed non-zero port is recommended so "
            "Claude Code keeps pointing at Graphify across restarts."
        ),
    ),
    ConfigFieldSpec(
        "GRAPHIFY_PYTHON_PATH",
        "Graphify Python Path",
        "graphify",
        settings_attr="graphify_python_path",
        default="",
        advanced=True,
        description="Optional Python interpreter to run graphify.serve.",
    ),
    ConfigFieldSpec(
        "GRAPHIFY_API_KEY",
        "Graphify API Key",
        "graphify",
        "secret",
        settings_attr="graphify_api_key",
        secret=True,
        description="API key for the Graphify HTTP transport.",
    ),
    ConfigFieldSpec(
        "GRAPHIFY_AUTO_INDEX_ON_START",
        "Auto-index on Start",
        "graphify",
        "boolean",
        settings_attr="graphify_auto_index_on_start",
        default="false",
        advanced=True,
        description="Re-index stale or errored projects when Graphify starts.",
    ),
    ConfigFieldSpec(
        "GRAPHIFY_AUTO_REINDEX",
        "Auto-reindex on Change",
        "graphify",
        "boolean",
        settings_attr="graphify_auto_reindex",
        default="false",
        advanced=True,
        description="Poll registered projects and re-index when files change.",
    ),
    ConfigFieldSpec(
        "GRAPHIFY_MAX_PROJECT_BYTES",
        "Max Project Size (bytes)",
        "graphify",
        "number",
        settings_attr="graphify_max_project_bytes",
        default=str(10 * 1024 * 1024 * 1024),
        advanced=True,
        description="Maximum project size allowed before indexing. 0 disables the guard.",
    ),
    ConfigFieldSpec(
        "GRAPHIFY_LLM_BACKEND",
        "Extraction LLM Backend",
        "graphify",
        "select",
        settings_attr="graphify_llm_backend",
        default="",
        options=(
            "",
            "cloudflare",
            "gemini",
            "deepseek",
            "kimi",
            "openai",
            "claude",
            "ollama",
            "lmstudio",
            "azure",
        ),
        description=(
            "LLM used for the semantic extraction pass over docs/PDFs/images and "
            "community naming. 'cloudflare' reuses the Cloudflare Workers AI key/"
            "account-id from the Providers tab; gemini/deepseek/kimi likewise reuse "
            "their provider key when the API key field below is empty. 'ollama' is "
            "fully local (no key). 'lmstudio' uses the local LM Studio server "
            "(no key, LM_STUDIO_BASE_URL). Leave empty with Code-Only on for no LLM."
        ),
    ),
    ConfigFieldSpec(
        "GRAPHIFY_LLM_MODEL",
        "Extraction Model",
        "graphify",
        "text",
        settings_attr="graphify_llm_model",
        default="",
        model_options=True,
        description=(
            "Model id passed to graphify as --model. For 'cloudflare' use a Workers AI "
            "model id (e.g. @cf/meta/llama-3.3-70b-instruct-fp8-fast); pick a "
            "vision-capable model (e.g. @cf/meta/llama-3.2-90b-vision-instruct) when "
            "the corpus contains images. Autocomplete mirrors the Model Config "
            "model fields."
        ),
    ),
    ConfigFieldSpec(
        "GRAPHIFY_LLM_API_KEY",
        "Extraction API Key",
        "graphify",
        "secret",
        settings_attr="graphify_llm_api_key",
        secret=True,
        description=(
            "API key for the extraction backend. Optional for cloudflare/gemini/"
            "deepseek/kimi, which fall back to the matching provider key. Required for "
            "openai/claude/azure. Ollama accepts any non-empty value."
        ),
    ),
    ConfigFieldSpec(
        "GRAPHIFY_CODE_ONLY",
        "Code-Only Index",
        "graphify",
        "boolean",
        settings_attr="graphify_code_only",
        default="false",
        description=(
            "Index code only via local AST parsing (no LLM API key). Skips "
            "docs/PDFs/images entirely."
        ),
    ),
    ConfigFieldSpec(
        "NVIDIA_NIM_PROXY",
        "NVIDIA NIM Proxy",
        "providers",
        "secret",
        settings_attr="nvidia_nim_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "OPENROUTER_PROXY",
        "OpenRouter Proxy",
        "providers",
        "secret",
        settings_attr="open_router_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "OPENROUTER_DATA_COLLECTION",
        "OpenRouter Data Collection (default)",
        "openrouter_policy",
        "select",
        settings_attr="open_router_data_collection",
        default="deny",
        options=("deny", "allow"),
        description=(
            "Per-request data_collection policy injected on every OpenRouter call. "
            "'deny' enforces Zero Data Retention (ZDR); 'allow' lets the upstream "
            "provider retain data. Defaults to 'deny' so paid models are always ZDR-strict."
        ),
    ),
    ConfigFieldSpec(
        "OPENROUTER_FREE_DATA_COLLECTION",
        "OpenRouter Data Collection (free models)",
        "openrouter_policy",
        "select",
        settings_attr="open_router_free_data_collection",
        default="allow",
        options=("deny", "allow"),
        description=(
            "Per-request data_collection policy used for OpenRouter model ids listed in "
            "OPENROUTER_FREE_MODEL_IDS. Almost all free endpoints on OpenRouter require "
            "allowing data collection, so this defaults to 'allow'."
        ),
    ),
    ConfigFieldSpec(
        "OPENROUTER_FREE_MODEL_IDS",
        "OpenRouter Free-Model Allowlist",
        "openrouter_policy",
        "textarea",
        settings_attr="open_router_free_model_ids",
        default="",
        description=(
            "Comma-separated exact OpenRouter model ids that get the free "
            "data-collection policy. Example: "
            "'meta-llama/llama-3.3-70b-instruct:free,deepseek/deepseek-chat:free'. "
            "Empty = no overrides (every call uses the default policy). The "
            "gateway enforces this server-side; client extra_body.provider "
            "overrides are ignored."
        ),
    ),
    ConfigFieldSpec(
        "MISTRAL_PROXY",
        "Mistral Proxy",
        "providers",
        "secret",
        settings_attr="mistral_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "CODESTRAL_PROXY",
        "Codestral Proxy",
        "providers",
        "secret",
        settings_attr="codestral_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "LMSTUDIO_PROXY",
        "LM Studio Proxy",
        "providers",
        "secret",
        settings_attr="lmstudio_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "LLAMACPP_PROXY",
        "llama.cpp Proxy",
        "providers",
        "secret",
        settings_attr="llamacpp_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "KIMI_PROXY",
        "Kimi Proxy",
        "providers",
        "secret",
        settings_attr="kimi_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "WAFER_PROXY",
        "Wafer Proxy",
        "providers",
        "secret",
        settings_attr="wafer_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "OPENCODE_PROXY",
        "OpenCode Zen Proxy",
        "providers",
        "secret",
        settings_attr="opencode_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "OPENCODE_GO_PROXY",
        "OpenCode Go Proxy",
        "providers",
        "secret",
        settings_attr="opencode_go_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "ZAI_PROXY",
        "Z.ai Proxy",
        "providers",
        "secret",
        settings_attr="zai_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "FIREWORKS_PROXY",
        "Fireworks Proxy",
        "providers",
        "secret",
        settings_attr="fireworks_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "GEMINI_PROXY",
        "Gemini Proxy",
        "providers",
        "secret",
        settings_attr="gemini_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "VERTEX_AI_PROXY",
        "Vertex AI Proxy",
        "providers",
        "secret",
        settings_attr="vertex_ai_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "GROQ_PROXY",
        "Groq Proxy",
        "providers",
        "secret",
        settings_attr="groq_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "CEREBRAS_PROXY",
        "Cerebras Proxy",
        "providers",
        "secret",
        settings_attr="cerebras_proxy",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "CLOUDFLARE_AI_BASE_URL",
        "Cloudflare Workers AI Base URL",
        "cloudflare",
        settings_attr="cloudflare_ai_base_url",
        default="",
        advanced=True,
        description=(
            "Optional full URL override for proxies, mocks, or self-hosted "
            "gateways. When set, ``CLOUDFLARE_AI_ACCOUNT_ID`` is **not** substituted "
            "into the URL — provide the complete endpoint including the account id "
            "segment. Empty falls back to "
            "``https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1``."
        ),
    ),
    ConfigFieldSpec(
        "CLOUDFLARE_AI_PROXY",
        "Cloudflare Workers AI Proxy",
        "cloudflare",
        "secret",
        settings_attr="cloudflare_ai_proxy",
        secret=True,
        advanced=True,
        description=(
            "HTTP(S) proxy for Cloudflare Workers AI requests. "
            "Format: ``http://user:pass@host:port``. "
            "Leave empty for direct connections."
        ),
    ),
    ConfigFieldSpec(
        "MODEL",
        "Default Model",
        "models",
        settings_attr="model",
        default="nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
        model_options=True,
        description="Fallback provider/model route for all Claude model names.",
    ),
    ConfigFieldSpec(
        "MODEL_OPUS",
        "Opus Override",
        "models",
        settings_attr="model_opus",
        model_options=True,
        description="Optional provider/model route for Opus requests.",
    ),
    ConfigFieldSpec(
        "MODEL_SONNET",
        "Sonnet Override",
        "models",
        settings_attr="model_sonnet",
        model_options=True,
        description="Optional provider/model route for Sonnet requests.",
    ),
    ConfigFieldSpec(
        "MODEL_HAIKU",
        "Haiku Override",
        "models",
        settings_attr="model_haiku",
        model_options=True,
        description="Optional provider/model route for Haiku requests.",
    ),
    ConfigFieldSpec(
        "ENABLE_MODEL_THINKING",
        "Enable Thinking",
        "thinking",
        "boolean",
        settings_attr="enable_model_thinking",
        default="true",
    ),
    ConfigFieldSpec(
        "ENABLE_OPUS_THINKING",
        "Opus Thinking",
        "thinking",
        "tri_boolean",
        settings_attr="enable_opus_thinking",
        description="Blank inherits Enable Thinking.",
    ),
    ConfigFieldSpec(
        "ENABLE_SONNET_THINKING",
        "Sonnet Thinking",
        "thinking",
        "tri_boolean",
        settings_attr="enable_sonnet_thinking",
        description="Blank inherits Enable Thinking.",
    ),
    ConfigFieldSpec(
        "ENABLE_HAIKU_THINKING",
        "Haiku Thinking",
        "thinking",
        "tri_boolean",
        settings_attr="enable_haiku_thinking",
        description="Blank inherits Enable Thinking.",
    ),
    ConfigFieldSpec(
        "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
        "Skip Permissions",
        "permissions",
        "boolean",
        default="false",
        description=(
            "Control the Claude Code permission bypass in ``~/.claude/settings.json``. "
            "When enabled, the settings file sets ``permissions.defaultMode`` to "
            "``bypassPermissions`` so managed Claude Code sessions skip tool "
            "approval prompts.  Disable to remove the setting and require "
            "interactive approval."
        ),
    ),
    ConfigFieldSpec(
        "CODEX_DANGEROUSLY_BYPASS_APPROVALS",
        "Codex Skip Approvals",
        "permissions",
        "boolean",
        settings_attr="codex_dangerously_bypass_approvals",
        default="true",
        description=(
            "Launch managed Codex CLI sessions with --dangerously-bypass-approvals-and-sandbox. "
            "Disable to require interactive approval."
        ),
    ),
    ConfigFieldSpec(
        "ANTHROPIC_AUTH_TOKEN",
        "API/CLI Auth Token",
        "runtime",
        "secret",
        settings_attr="anthropic_auth_token",
        default="",
        secret=True,
        description="Protects Claude/API access. It is not admin-page login.",
    ),
    ConfigFieldSpec(
        "PROVIDER_RATE_LIMIT",
        "Provider Rate Limit",
        "runtime",
        "number",
        settings_attr="provider_rate_limit",
        default="40",
        description="Max requests per window. 0 disables proactive limiting.",
    ),
    ConfigFieldSpec(
        "PROVIDER_RATE_WINDOW",
        "Provider Rate Window",
        "runtime",
        "number",
        settings_attr="provider_rate_window",
        default="60",
        description="Window in seconds for the proactive rate limit.",
    ),
    ConfigFieldSpec(
        "PROVIDER_MAX_CONCURRENCY",
        "Provider Max Concurrency",
        "runtime",
        "number",
        settings_attr="provider_max_concurrency",
        default="5",
    ),
    ConfigFieldSpec(
        "HTTP_READ_TIMEOUT",
        "HTTP Read Timeout",
        "runtime",
        "number",
        settings_attr="http_read_timeout",
        default="120",
    ),
    ConfigFieldSpec(
        "HTTP_WRITE_TIMEOUT",
        "HTTP Write Timeout",
        "runtime",
        "number",
        settings_attr="http_write_timeout",
        default="10",
    ),
    ConfigFieldSpec(
        "HTTP_CONNECT_TIMEOUT",
        "HTTP Connect Timeout",
        "runtime",
        "number",
        settings_attr="http_connect_timeout",
        default="60",
    ),
    ConfigFieldSpec(
        "HOST",
        "Server Host",
        "runtime",
        settings_attr="host",
        default="0.0.0.0",
        restart_required=True,
    ),
    ConfigFieldSpec(
        "PORT",
        "Server Port",
        "runtime",
        "number",
        settings_attr="port",
        default="8082",
        restart_required=True,
    ),
    ConfigFieldSpec(
        "MESSAGING_PLATFORM",
        "Messaging Platform",
        "messaging",
        "select",
        settings_attr="messaging_platform",
        default="discord",
        options=("telegram", "discord", "none"),
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "MESSAGING_RATE_LIMIT",
        "Messaging Rate Limit",
        "messaging",
        "number",
        settings_attr="messaging_rate_limit",
        default="1",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "MESSAGING_RATE_WINDOW",
        "Messaging Rate Window",
        "messaging",
        "number",
        settings_attr="messaging_rate_window",
        default="1",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "TELEGRAM_BOT_TOKEN",
        "Telegram Bot Token",
        "messaging",
        "secret",
        settings_attr="telegram_bot_token",
        secret=True,
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "ALLOWED_TELEGRAM_USER_ID",
        "Allowed Telegram User ID",
        "messaging",
        settings_attr="allowed_telegram_user_id",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "DISCORD_BOT_TOKEN",
        "Discord Bot Token",
        "messaging",
        "secret",
        settings_attr="discord_bot_token",
        secret=True,
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "ALLOWED_DISCORD_CHANNELS",
        "Allowed Discord Channels",
        "messaging",
        settings_attr="allowed_discord_channels",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "ALLOWED_DIR",
        "Allowed Directory",
        "messaging",
        settings_attr="allowed_dir",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "MAX_MESSAGE_LOG_ENTRIES_PER_CHAT",
        "Max Message Log Entries",
        "messaging",
        "number",
        settings_attr="max_message_log_entries_per_chat",
        advanced=True,
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "VOICE_NOTE_ENABLED",
        "Voice Notes",
        "voice",
        "boolean",
        settings_attr="voice_note_enabled",
        default="true",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "WHISPER_DEVICE",
        "Whisper Device",
        "voice",
        "select",
        settings_attr="whisper_device",
        default="cpu",
        options=("cpu", "cuda", "nvidia_nim"),
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "WHISPER_MODEL",
        "Whisper Model",
        "voice",
        settings_attr="whisper_model",
        default="base",
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "HF_TOKEN",
        "Hugging Face Token",
        "voice",
        "secret",
        settings_attr="hf_token",
        secret=True,
        session_sensitive=True,
    ),
    ConfigFieldSpec(
        "FAST_PREFIX_DETECTION",
        "Fast Prefix Detection",
        "runtime",
        "boolean",
        settings_attr="fast_prefix_detection",
        default="true",
        advanced=True,
    ),
    ConfigFieldSpec(
        "ENABLE_NETWORK_PROBE_MOCK",
        "Network Probe Mock",
        "runtime",
        "boolean",
        settings_attr="enable_network_probe_mock",
        default="true",
        advanced=True,
    ),
    ConfigFieldSpec(
        "ENABLE_TITLE_GENERATION_SKIP",
        "Title Generation Skip",
        "runtime",
        "boolean",
        settings_attr="enable_title_generation_skip",
        default="true",
        advanced=True,
    ),
    ConfigFieldSpec(
        "ENABLE_SUGGESTION_MODE_SKIP",
        "Suggestion Mode Skip",
        "runtime",
        "boolean",
        settings_attr="enable_suggestion_mode_skip",
        default="true",
        advanced=True,
    ),
    ConfigFieldSpec(
        "ENABLE_FILEPATH_EXTRACTION_MOCK",
        "Filepath Extraction Mock",
        "runtime",
        "boolean",
        settings_attr="enable_filepath_extraction_mock",
        default="true",
        advanced=True,
    ),
    ConfigFieldSpec(
        "CONCISE_OUTPUT",
        "Concise Output Directive",
        "runtime",
        "boolean",
        settings_attr="concise_output",
        default="true",
        description=(
            "Append a short concise-output directive to every request's "
            "system prompt to reduce output tokens (~5x input cost)."
        ),
    ),
    ConfigFieldSpec(
        "CONCISE_OUTPUT_DIRECTIVE",
        "Concise Directive Text",
        "runtime",
        "textarea",
        settings_attr="concise_output_directive",
        advanced=True,
        description="Custom directive text; empty uses the built-in default.",
    ),
    # ==================== Advanced routing ====================
    ConfigFieldSpec(
        "FORWARD_ANTHROPIC_BETA",
        "Forward Anthropic Beta Header",
        "runtime",
        "boolean",
        settings_attr="forward_anthropic_beta",
        default="true",
        advanced=True,
        description=(
            "Forward the client's ``anthropic-beta`` header to providers with "
            "native Anthropic Messages endpoints so beta features (e.g. "
            "fine-grained tool streaming) stay enabled end-to-end."
        ),
    ),
    ConfigFieldSpec(
        "PROMPT_CACHE_KEY_PROVIDERS",
        "Prompt Cache Key Providers",
        "runtime",
        settings_attr="prompt_cache_key_providers",
        default="",
        advanced=True,
        description=(
            "Comma-separated provider ids that receive a stable "
            "`prompt_cache_key` on /chat/completions requests for cache "
            "affinity routing. Empty = only providers that opt in via code."
        ),
    ),
    ConfigFieldSpec(
        "TOKEN_COUNT_MULTIPLIER",
        "Token Count Multiplier",
        "runtime",
        "number",
        settings_attr="token_count_multiplier",
        default="1.15",
        advanced=True,
        description=(
            "Multiplier applied to /v1/messages/count_tokens responses to "
            "correct tiktoken's undercount vs the Anthropic tokenizer."
        ),
    ),
    ConfigFieldSpec(
        "LONG_CONTEXT_MODEL",
        "Long Context Fallback Model",
        "models",
        settings_attr="long_context_model",
        default="",
        model_options=True,
        advanced=True,
        description=(
            "Provider/model ref to reroute oversized requests to. Empty disables."
        ),
    ),
    ConfigFieldSpec(
        "LONG_CONTEXT_THRESHOLD_TOKENS",
        "Long Context Threshold Tokens",
        "models",
        "number",
        settings_attr="long_context_threshold_tokens",
        default="0",
        advanced=True,
        description=(
            "Token threshold that triggers long-context fallback. 0 disables."
        ),
    ),
    ConfigFieldSpec(
        "PROVIDER_HTTP2",
        "Provider HTTP/2",
        "runtime",
        "boolean",
        settings_attr="provider_http2",
        default="false",
        advanced=True,
        description="Opt-in HTTP/2 for provider HTTP clients.",
    ),
    ConfigFieldSpec(
        "ENABLE_WEB_SERVER_TOOLS",
        "Web Server Tools",
        "web_tools",
        "boolean",
        settings_attr="enable_web_server_tools",
        default="false",
    ),
    ConfigFieldSpec(
        "WEB_FETCH_ALLOWED_SCHEMES",
        "Allowed Web Fetch Schemes",
        "web_tools",
        settings_attr="web_fetch_allowed_schemes",
        default="http,https",
    ),
    ConfigFieldSpec(
        "WEB_FETCH_ALLOW_PRIVATE_NETWORKS",
        "Allow Private Networks",
        "web_tools",
        "boolean",
        settings_attr="web_fetch_allow_private_networks",
        default="false",
    ),
    ConfigFieldSpec(
        "LOG_LEVEL",
        "Log Level",
        "diagnostics",
        "select",
        settings_attr="log_level",
        default="INFO",
        options=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        restart_required=True,
        description="Minimum level for the JSON log sink.",
    ),
    ConfigFieldSpec(
        "TRACE_FULL_PAYLOADS",
        "Trace Full Payloads",
        "diagnostics",
        "boolean",
        settings_attr="trace_full_payloads",
        default="false",
        advanced=True,
        description=(
            "Log conversation text verbatim in TRACE snapshots instead of "
            "truncated previews."
        ),
    ),
    ConfigFieldSpec(
        "DEBUG_PLATFORM_EDITS",
        "Debug Platform Edits",
        "diagnostics",
        "boolean",
        settings_attr="debug_platform_edits",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "DEBUG_SUBAGENT_STACK",
        "Debug Subagent Stack",
        "diagnostics",
        "boolean",
        settings_attr="debug_subagent_stack",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_RAW_API_PAYLOADS",
        "Log Raw API Payloads",
        "diagnostics",
        "boolean",
        settings_attr="log_raw_api_payloads",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_RAW_SSE_EVENTS",
        "Log Raw SSE Events",
        "diagnostics",
        "boolean",
        settings_attr="log_raw_sse_events",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_API_ERROR_TRACEBACKS",
        "Log API Error Tracebacks",
        "diagnostics",
        "boolean",
        settings_attr="log_api_error_tracebacks",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_RAW_MESSAGING_CONTENT",
        "Log Raw Messaging Content",
        "diagnostics",
        "boolean",
        settings_attr="log_raw_messaging_content",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_RAW_CLI_DIAGNOSTICS",
        "Log Raw CLI Diagnostics",
        "diagnostics",
        "boolean",
        settings_attr="log_raw_cli_diagnostics",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "LOG_MESSAGING_ERROR_DETAILS",
        "Log Messaging Error Details",
        "diagnostics",
        "boolean",
        settings_attr="log_messaging_error_details",
        default="false",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_NVIDIA_NIM",
        "Smoke NVIDIA NIM Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_OPEN_ROUTER",
        "Smoke OpenRouter Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_MISTRAL",
        "Smoke Mistral Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_MISTRAL_CODESTRAL",
        "Smoke Mistral Codestral Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_DEEPSEEK",
        "Smoke DeepSeek Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_LMSTUDIO",
        "Smoke LM Studio Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_LLAMACPP",
        "Smoke llama.cpp Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_OLLAMA",
        "Smoke Ollama Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_KIMI",
        "Smoke Kimi Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_WAFER",
        "Smoke Wafer Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_OPENCODE",
        "Smoke OpenCode Zen Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_OPENCODE_GO",
        "Smoke OpenCode Go Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_ZAI",
        "Smoke Z.ai Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_FIREWORKS",
        "Smoke Fireworks Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_GEMINI",
        "Smoke Gemini Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_GROQ",
        "Smoke Groq Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_CEREBRAS",
        "Smoke Cerebras Model",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_MODEL_CLOUDFLARE_AI",
        "Smoke Cloudflare Workers AI Model",
        "cloudflare",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_NIM_MODELS",
        "Smoke NIM Models",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_NIM_EXTRA_MODELS",
        "Smoke NIM Extra Models",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_OPENROUTER_FREE_MODELS",
        "Smoke OpenRouter Free Models",
        "smoke",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SMOKE_OPENROUTER_FREE_EXTRA_MODELS",
        "Smoke OpenRouter Free Extra Models",
        "smoke",
        advanced=True,
    ),
    # -- SFTP shared MCP config --
    ConfigFieldSpec(
        "FCC_SFTP_HOST",
        "SFTP Host",
        "mcp_shared",
        settings_attr="sftp_host",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_PORT",
        "SFTP Port",
        "mcp_shared",
        "number",
        settings_attr="sftp_port",
        default="22",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_USERNAME",
        "SFTP Username",
        "mcp_shared",
        settings_attr="sftp_username",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_AUTH_METHOD",
        "SFTP Auth Method",
        "mcp_shared",
        "select",
        settings_attr="sftp_auth_method",
        default="password",
        options=("password", "key"),
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_PASSWORD",
        "SFTP Password",
        "mcp_shared",
        "secret",
        settings_attr="sftp_password",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_PRIVATE_KEY",
        "SFTP Private Key",
        "mcp_shared",
        "textarea",
        settings_attr="sftp_private_key",
        secret=True,
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_REMOTE_FILE_PATH",
        "SFTP Remote File Path",
        "mcp_shared",
        settings_attr="sftp_remote_file_path",
        advanced=True,
    ),
    ConfigFieldSpec(
        "FCC_SFTP_ENABLED",
        "SFTP Enabled",
        "mcp_shared",
        "boolean",
        settings_attr="sftp_enabled",
        default="false",
        restart_required=True,
        advanced=True,
    ),
)

FIELD_BY_KEY = {field.key: field for field in FIELDS}


def env_keys() -> frozenset[str]:
    """Return env keys owned by the admin manifest."""

    return frozenset(field.key for field in FIELDS)


def fields_with_attrs() -> Iterable[ConfigFieldSpec]:
    """Yield fields that validate through Settings."""

    return (field for field in FIELDS if field.settings_attr is not None)
