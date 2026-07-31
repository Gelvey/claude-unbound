# Settings Reference

Environment variables grouped by concern. Set them in `~/.fcc/.env` or via the Admin UI at `/admin`.

## Providers

| Variable | Description |
|---|---|
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM API key (build.nvidia.com) |
| `OPENROUTER_API_KEY` | OpenRouter API key (openrouter.ai/keys) |
| `GEMINI_API_KEY` | Google AI Studio / Gemini API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `MISTRAL_API_KEY` | Mistral La Plateforme API key |
| `CODESTRAL_API_KEY` | Mistral Codestral API key (separate from La Plateforme) |
| `OPENCODE_API_KEY` | OpenCode Zen + Go API key (opencode.ai/auth) |
| `WAFER_API_KEY` | Wafer API key (wafer.ai) |
| `KIMI_API_KEY` | Kimi / Moonshot API key |
| `CEREBRAS_API_KEY` | Cerebras Inference API key |
| `CLOUDFLARE_AI_API_KEY` | Cloudflare Workers AI API token |
| `CLOUDFLARE_AI_ACCOUNT_ID` | Cloudflare account ID (used in upstream URL) |
| `CLOUDFLARE_AI_BASE_URL` | Optional full URL override for Cloudflare AI |
| `GROQ_API_KEY` | Groq API key |
| `FIREWORKS_API_KEY` | Fireworks AI API key |
| `ZAI_API_KEY` | Z.ai API key |
| `LM_STUDIO_BASE_URL` | LM Studio server URL (default: `http://localhost:1234/v1`) |
| `LLAMACPP_BASE_URL` | llama.cpp server URL (default: `http://localhost:8080/v1`) |
| `OLLAMA_BASE_URL` | Ollama server root URL (default: `http://localhost:11434`, no `/v1`) |
| `FREEBUFF_ENABLED` | Enable the Freebuff2API local provider (default: `false`) |
| `FREEBUFF_BASE_URL` | Freebuff2API base URL (default: `http://127.0.0.1:8080/v1`) |
| `FREEBUFF_CREDENTIALS_PATH` | Path to Freebuff credentials file (default: `~/.config/manicode/credentials.json`) |

## Models

| Variable | Description |
|---|---|
| `MODEL` | Fallback model slug, format `provider_type/model/name` |
| `MODEL_OPUS` | Override for Claude Opus requests (optional) |
| `MODEL_SONNET` | Override for Claude Sonnet requests (optional) |
| `MODEL_HAIKU` | Override for Claude Haiku requests (optional) |
| `LONG_CONTEXT_MODEL` | Reroute long-context requests to this model (optional) |
| `LONG_CONTEXT_THRESHOLD_TOKENS` | Token threshold for long-context rerouting (0 disables) |

## Per-Provider Proxy

| Variable | Description |
|---|---|
| `NVIDIA_NIM_PROXY` | HTTP/socks5 proxy for NVIDIA NIM requests |
| `OPENROUTER_PROXY` | HTTP/socks5 proxy for OpenRouter requests |
| `MISTRAL_PROXY` | HTTP/socks5 proxy for Mistral requests |
| `CODESTRAL_PROXY` | HTTP/socks5 proxy for Codestral requests |
| `LMSTUDIO_PROXY` | HTTP/socks5 proxy for LM Studio requests |
| `LLAMACPP_PROXY` | HTTP/socks5 proxy for llama.cpp requests |
| `KIMI_PROXY` | HTTP/socks5 proxy for Kimi requests |
| `WAFER_PROXY` | HTTP/socks5 proxy for Wafer requests |
| `OPENCODE_PROXY` | HTTP/socks5 proxy for OpenCode Zen requests |
| `OPENCODE_GO_PROXY` | HTTP/socks5 proxy for OpenCode Go requests |
| `ZAI_PROXY` | HTTP/socks5 proxy for Z.ai requests |
| `FIREWORKS_PROXY` | HTTP/socks5 proxy for Fireworks AI requests |
| `GEMINI_PROXY` | HTTP/socks5 proxy for Gemini requests |
| `GROQ_PROXY` | HTTP/socks5 proxy for Groq requests |
| `CEREBRAS_PROXY` | HTTP/socks5 proxy for Cerebras requests |
| `CLOUDFLARE_AI_PROXY` | HTTP/socks5 proxy for Cloudflare AI requests |
| `FREEBUFF_PROXY` | HTTP/socks5 proxy for Freebuff requests |

## Thinking / Reasoning

| Variable | Description |
|---|---|
| `ENABLE_MODEL_THINKING` | Enable thinking/reasoning for all models (default: `true`) |
| `ENABLE_OPUS_THINKING` | Override for Opus (blank inherits `ENABLE_MODEL_THINKING`) |
| `ENABLE_SONNET_THINKING` | Override for Sonnet (blank inherits `ENABLE_MODEL_THINKING`) |
| `ENABLE_HAIKU_THINKING` | Override for Haiku (blank inherits `ENABLE_MODEL_THINKING`) |

## Rate Limiting

| Variable | Description |
|---|---|
| `PROVIDER_RATE_LIMIT` | Max requests per window across all providers (0 disables proactive limiting) |
| `PROVIDER_RATE_WINDOW` | Sliding window size in seconds (default: 60) |
| `PROVIDER_MAX_CONCURRENCY` | Max concurrent in-flight requests (default: 5) |

## HTTP Client

| Variable | Description |
|---|---|
| `HTTP_READ_TIMEOUT` | Read timeout in seconds (default: 120) |
| `HTTP_WRITE_TIMEOUT` | Write timeout in seconds (default: 10) |
| `HTTP_CONNECT_TIMEOUT` | Connect timeout in seconds (default: 60) |
| `PROVIDER_HTTP2` | Opt-in HTTP/2 for provider clients (default: `false`) |
| `TOKEN_COUNT_MULTIPLIER` | Multiplier for count_tokens responses to correct tiktoken vs Anthropic tokenizer (default: 1.15) |

## OpenRouter Policy

| Variable | Description |
|---|---|
| `OPENROUTER_DATA_COLLECTION` | Default `data_collection` policy for all OpenRouter calls (`deny` or `allow`) |
| `OPENROUTER_FREE_DATA_COLLECTION` | Override for model ids in the free allowlist (`deny` or `allow`) |
| `OPENROUTER_FREE_MODEL_IDS` | Comma-separated OpenRouter model ids that use the free data-collection policy |

## Messaging

| Variable | Description |
|---|---|
| `MESSAGING_PLATFORM` | Bot platform: `discord`, `telegram`, or `none` (default: `discord`) |
| `MESSAGING_RATE_LIMIT` | Max messages per window (default: 1) |
| `MESSAGING_RATE_WINDOW` | Rate-limit window in seconds (default: 1.0) |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `ALLOWED_DISCORD_CHANNELS` | Comma-separated Discord channel IDs |
| `TELEGRAM_BOT_TOKEN` (via settings) | Telegram bot token |
| `ALLOWED_TELEGRAM_USER_ID` (via settings) | Telegram user ID allowed to use the bot |
| `MAX_MESSAGE_LOG_ENTRIES_PER_CHAT` | Max message log entries per chat (optional) |

## Voice Notes

| Variable | Description |
|---|---|
| `VOICE_NOTE_ENABLED` | Enable voice note transcription (default: `true`) |
| `WHISPER_DEVICE` | Transcription device: `cpu`, `cuda`, or `nvidia_nim` |
| `WHISPER_MODEL` | Whisper model ID (e.g. `base`, `large-v3-turbo`, `nvidia/parakeet-ctc-1.1b-asr`) |
| `HF_TOKEN` | Hugging Face token for faster Whisper model downloads (optional) |

## MCP Router

| Variable | Description |
|---|---|
| `MCP_CONFIG` | Path to MCP router config (default: `~/.fcc/mcp_config.json`) |

## Graphify

| Variable | Description |
|---|---|
| `GRAPHIFY_ENABLED` | Enable Graphify knowledge-graph integration (default: `false`) |
| `GRAPHIFY_SERVER_PORT` | Port for local Graphify MCP HTTP server (default: 7120) |
| `GRAPHIFY_PYTHON_PATH` | Optional Python interpreter for graphify.serve |
| `GRAPHIFY_API_KEY` | Optional bearer auth for the local Graphify server |
| `GRAPHIFY_STATELESS` | Run Graphify in stateless mode (default: `true`) |
| `GRAPHIFY_LLM_BACKEND` | LLM backend for semantic extraction (`cloudflare`, `gemini`, `deepseek`, `kimi`, `openai`, `claude`, `ollama`, `lmstudio`, `azure`) |
| `GRAPHIFY_LLM_API_KEY` | API key for the configured LLM backend (optional; falls back to matching provider key) |
| `GRAPHIFY_LLM_MODEL` | Model id passed to graphify extract |
| `GRAPHIFY_CODE_ONLY` | Index code only via local AST parsing, skip docs/PDFs/images (default: `false`) |
| `GRAPHIFY_AUTO_INDEX_ON_START` | Auto-index projects on server start (default: `false`) |
| `GRAPHIFY_MAX_PROJECT_BYTES` | Max allowed project size in bytes (default: 10 GiB) |
| `GRAPHIFY_AUTO_REINDEX` | Poll projects and re-index on file changes (default: `false`) |
| `GRAPHIFY_TOKEN_BUDGET` | Per-chunk token budget for graphify extract (default: 60000) |

## Server

| Variable | Description |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | Server API key; when empty, auth is disabled |
| `HOST` | Bind address (default: `0.0.0.0`) |
| `PORT` | Listen port (default: `8082`) |

## CLI Permission Bypass

| Variable | Description |
|---|---|
| `CODEX_DANGEROUSLY_BYPASS_APPROVALS` | Skip approval prompts in managed Codex CLI sessions (default: `true`) |
| `CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS` | Skip permission prompts in managed Claude Code CLI sessions (default: `true`) |

## Output Shaping

| Variable | Description |
|---|---|
| `CONCISE_OUTPUT` | Append a concise-output directive to every chat request system prompt (default: `true`) |
| `CONCISE_OUTPUT_DIRECTIVE` | Custom directive text (blank falls back to built-in) |

## Web Server Tools

| Variable | Description |
|---|---|
| `ENABLE_WEB_SERVER_TOOLS` | Enable local web_search / web_fetch tools (default: `false`, SSRF risk) |
| `WEB_FETCH_ALLOWED_SCHEMES` | Comma-separated URL schemes allowed for web_fetch (default: `http,https`) |
| `WEB_FETCH_ALLOW_PRIVATE_NETWORKS` | Skip private/loopback IP blocking for web_fetch (default: `false`) |

## Debug / Logging

| Variable | Description |
|---|---|
| `LOG_LEVEL` | Minimum log level: `TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`) |
| `TRACE_FULL_PAYLOADS` | Log full verbatim conversation text in trace snapshots (default: `false`) |
| `LOG_RAW_API_PAYLOADS` | Log full API request/response payloads (default: `false`) |
| `LOG_RAW_SSE_EVENTS` | Log raw SSE event lines (default: `false`) |
| `LOG_API_ERROR_TRACEBACKS` | Log exception tracebacks in API errors (default: `false`) |
| `LOG_RAW_MESSAGING_CONTENT` | Log messaging text/transcription previews (default: `false`) |
| `LOG_RAW_CLI_DIAGNOSTICS` | Log full Claude CLI stderr and parser errors (default: `false`) |
| `LOG_MESSAGING_ERROR_DETAILS` | Log exception text in messaging (default: `false`) |
| `DEBUG_PLATFORM_EDITS` | Debug platform edit events (default: `false`) |
| `DEBUG_SUBAGENT_STACK` | Debug subagent stack traces (default: `false`) |

## SFTP MCP

| Variable | Description |
|---|---|
| `FCC_SFTP_ENABLED` | Enable the SFTP shared MCP backend (default: `false`) |
| `FCC_SFTP_HOST` | SFTP server hostname |
| `FCC_SFTP_PORT` | SFTP port (default: 22) |
| `FCC_SFTP_USERNAME` | SFTP username |
| `FCC_SFTP_AUTH_METHOD` | Auth method: `password` or `key` (default: `password`) |
| `FCC_SFTP_PASSWORD` | SFTP password (when auth method is `password`) |
| `FCC_SFTP_PRIVATE_KEY` | SFTP private key (when auth method is `key`) |
| `FCC_SFTP_REMOTE_FILE_PATH` | Remote file path for the SFTP MCP backend |

## Anthropic Beta

| Variable | Description |
|---|---|
| `FORWARD_ANTHROPIC_BETA` | Forward the client's `anthropic-beta` header to Anthropic Messages providers (default: `true`) |

## Prompt Cache

| Variable | Description |
|---|---|
| `PROMPT_CACHE_KEY_PROVIDERS` | Comma-separated provider ids that receive a stable `prompt_cache_key` for cache-affinity routing |
