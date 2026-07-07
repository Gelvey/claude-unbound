"""Shared defaults used by config models and provider adapters."""

# HTTP client connect timeout (seconds). Keep aligned with README.md and .env.example.
HTTP_CONNECT_TIMEOUT_DEFAULT = 10.0

# HTTP keep-alive expiry (seconds). httpx defaults to 5s, which forces a fresh
# TCP+TLS handshake on every request whenever inference takes longer than the
# keep-alive window (common with large / free-tier models).
HTTP_KEEPALIVE_EXPIRY_DEFAULT = 600.0

# Minimum HTTP connection pool size regardless of provider max_concurrency.
HTTP_MIN_POOL_SIZE = 20

# Anthropic Messages API default when the client omits max_tokens.
ANTHROPIC_DEFAULT_MAX_OUTPUT_TOKENS = 81920

# Max bytes read from a non-200 native messages response when verbose error logging is on.
NATIVE_MESSAGES_ERROR_BODY_LOG_CAP_BYTES = 4096

# Max upstream error bytes shown to users for copy/paste diagnostics.
PROVIDER_ERROR_BODY_DISPLAY_CAP_BYTES = 16384
