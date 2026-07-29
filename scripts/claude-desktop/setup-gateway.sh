#!/bin/bash
# ==============================================================================
# setup-gateway.sh — Wire Claude Desktop (unofficial) into the Claude Unbound
# proxy gateway via managed MDM settings.
#
# What this does:
#   Writes /etc/claude-desktop/managed-settings.json so the unofficial Claude
#   Desktop app (https://github.com/aaddrick/claude-desktop-debian, binary
#   /usr/bin/claude-desktop-unofficial, StartupWMClass com.anthropic.Claude)
#   routes inference through the local fcc-server proxy instead of calling
#   api.anthropic.com directly.  In gateway mode the desktop app does NOT
#   prompt for a claude.ai login — the gateway credential is used instead.
#   Chat/Cowork tabs requiring a claude.ai identity are unavailable.
#
# Managed-settings.json is the MDM/managed configuration path.  When present
# the file is read once at launch and its keys override the in-app form
# (managed keys become read-only in the UI).  The file must be a regular file
# (not a symlink), owned by root, and not group-/world-writable; the parent
# directory /etc/claude-desktop must also be root-owned.
#
# Troubleshooting note:
#   If you later flip "toolSearchEnabled" on in the desktop app and see
#   HTTP 400 responses, that is the gateway rejecting beta headers.
#   Leave tool search off when using gateway mode.
#
# Usage:
#   setup-gateway.sh            Write/refresh the managed settings file.
#   setup-gateway.sh --check    Exit 0 if gateway is wired, 1 otherwise.
#   setup-gateway.sh --unwire   Remove the managed settings file.
#   setup-gateway.sh --help     Show this help.
#
# Idempotent: re-running produces the same managed file.
# Portable: no bash 4+ features (no declare -A); works on bash 3.2 (macOS).
# ==============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Path derivation — location-portable, never hardcodes $HOME.
# ---------------------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# ---------------------------------------------------------------------------
# Dotenv helpers — read KEY=VALUE from ~/.fcc/.env without `source`, since the
# file may contain unquoted values or comments. Defined before first use so the
# top-level env-reading below can reuse them.
#   _env_val <key> [env_file]   -> value on stdout (empty if missing)
# ---------------------------------------------------------------------------
FCC_ENV="${HOME}/.fcc/.env"

_env_val() {
    local key="$1"
    local file="${2:-$FCC_ENV}"
    [ -f "$file" ] || return 0
    grep -E "^${key}=" "$file" 2>/dev/null | tail -1 \
        | sed -E "s/^${key}=//; s/^\"(.*)\"$/\1/; s/^'(.*)'$/\1/" || true
}

# Build a deduped, ordered JSON array of gateway model IDs from the chat
# model env vars (MODEL, MODEL_OPUS, MODEL_SONNET, MODEL_HAIKU). Each
# non-empty ref becomes "anthropic/{ref}", mirroring gateway_model_id() in
# api/gateway_model_ids.py and the refs returned by
# settings.configured_chat_model_refs(). MODEL is the default and stays
# first; duplicate refs are dropped. Emits a compact JSON array on stdout,
# or nothing if MODEL is absent/empty (the caller then falls back to the
# proxy /v1/models fetch). Args: [env_file]
_curated_models_json() {
    local file="${1:-$FCC_ENV}"
    local model opus sonnet haiku ref
    model="$(_env_val MODEL "$file")"
    opus="$(_env_val MODEL_OPUS "$file")"
    sonnet="$(_env_val MODEL_SONNET "$file")"
    haiku="$(_env_val MODEL_HAIKU "$file")"

    # Without the default model the curated list is not meaningful.
    [ -n "$model" ] || return 0

    {
        for ref in "$model" "$opus" "$sonnet" "$haiku"; do
            [ -n "$ref" ] || continue
            printf 'anthropic/%s\n' "$ref"
        done
    } | awk '!seen[$0]++' | jq -R -s -c 'split("\n") | map(select(length > 0))'
}

# Defaults; overridden from ~/.fcc/.env below.
AUTH_TOKEN="freecc"
PORT="8082"

_val="$(_env_val PORT)";        [ -n "$_val" ] && PORT="$_val"
_val="$(_env_val ANTHROPIC_AUTH_TOKEN)"; [ -n "$_val" ] && AUTH_TOKEN="$_val"

BASE_URL="http://localhost:${PORT}"
MANAGED_DIR="/etc/claude-desktop"
MANAGED_FILE="${MANAGED_DIR}/managed-settings.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

print_help() {
    cat <<EOF
setup-gateway.sh — Wire Claude Desktop (unofficial) into the Claude Unbound proxy.

Usage:
  setup-gateway.sh            Write or refresh the managed settings file
                              so the desktop app routes through the gateway.
  setup-gateway.sh --check    Exit 0 if the gateway is wired, 1 otherwise.
  setup-gateway.sh --unwire   Remove the managed settings file (revert to
                              default Anthropic login + editable 3P form).
  setup-gateway.sh --help     Show this help.

Environment:
  Reads ANTHROPIC_AUTH_TOKEN and PORT from ~/.fcc/.env
  (falls back to "freecc" and "8082").

Notes:
  - In gateway mode the desktop app does not prompt for a claude.ai login.
    The gateway credential is used instead.  Chat/Cowork tabs requiring a
    claude.ai identity are unavailable.
  - If you later enable "toolSearchEnabled" and see HTTP 400 errors, that
    is the gateway rejecting beta headers.  Leave tool search off.
  - Quit and reopen Claude Desktop for changes to take effect.
EOF
}

# Check for a privilege-elevation tool and return its prefix.
priv_prefix() {
    if command -v sudo >/dev/null 2>&1; then
        printf "sudo"
    elif command -v pkexec >/dev/null 2>&1; then
        printf "pkexec"
    else
        printf ""
    fi
}

# ---------------------------------------------------------------------------
# Mode: --check
# ---------------------------------------------------------------------------
do_check() {
    if [ ! -f "$MANAGED_FILE" ]; then
        echo "not wired: managed settings file absent"
        exit 1
    fi

    # Verify the gateway base URL matches our expected localhost:PORT.
    if command -v jq >/dev/null 2>&1; then
        _stored=""
        _stored="$(jq -r '.inferenceGatewayBaseUrl // ""' "$MANAGED_FILE" 2>/dev/null || true)"
        if [ "$_stored" != "$BASE_URL" ]; then
            echo "not wired: inferenceGatewayBaseUrl='${_stored}' (expected '${BASE_URL}')"
            exit 1
        fi

        # When a curated model list can be derived from the env, also verify
        # inferenceModels matches it — a stale or absent list means the
        # picker would fall back to auto-discovery (flooding it with the
        # provider's full catalog). Re-run setup-gateway.sh to refresh.
        _curated=""
        _curated="$(_curated_models_json)"
        if [ -n "$_curated" ]; then
            _stored_models=""
            _stored_models="$(jq -c '.inferenceModels // []' "$MANAGED_FILE" 2>/dev/null || echo "[]")"
            if [ "$_stored_models" != "$_curated" ]; then
                _count="$(printf '%s' "$_curated" | jq 'length')"
                echo "not wired: inferenceModels stale (expected ${_count} curated models)"
                exit 1
            fi
        fi

        echo "wired: gateway=${BASE_URL}"
        exit 0
    else
        # Fallback: grep for the base URL in the JSON.
        if grep -q "\"${BASE_URL}\"" "$MANAGED_FILE" 2>/dev/null; then
            echo "wired: gateway=${BASE_URL}"
            exit 0
        else
            echo "not wired: base URL not found in managed settings"
            exit 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# Mode: --unwire
# ---------------------------------------------------------------------------
do_unwire() {
    if [ ! -f "$MANAGED_FILE" ]; then
        echo "Managed settings file not present — nothing to unwire."
        exit 0
    fi

    _priv="$(priv_prefix)"
    if [ -z "$_priv" ]; then
        echo "Error: need sudo or pkexec to remove ${MANAGED_FILE}" >&2
        exit 1
    fi

    $_priv rm -f "$MANAGED_FILE"
    echo "Removed ${MANAGED_FILE}."
    echo "Claude Desktop reverts to default Anthropic login + editable 3P form."
    echo "Quit and reopen Claude Desktop for changes to take effect."
    exit 0
}

# ---------------------------------------------------------------------------
# Mode: write/refresh (default)
# ---------------------------------------------------------------------------
do_write() {
    # jq is required for safe JSON construction.
    if ! command -v jq >/dev/null 2>&1; then
        echo "Error: jq is required but not installed." >&2
        echo "Install it with your package manager, e.g.:" >&2
        echo "  apt install jq   (Debian/Ubuntu)" >&2
        echo "  brew install jq   (macOS)" >&2
        exit 1
    fi

    # Privilege elevation is required to write under /etc.
    _priv="$(priv_prefix)"
    if [ -z "$_priv" ]; then
        echo "Error: need sudo or pkexec to write under ${MANAGED_DIR}" >&2
        exit 1
    fi

    # Build the model list for the picker. Prefer a curated list derived from
    # the chat model env vars (MODEL/MODEL_OPUS/MODEL_SONNET/MODEL_HAIKU):
    # it works even when the proxy is down (the launcher runs this script
    # before fcc-server starts) and keeps the picker to the few models the
    # user actually configured instead of the provider's full catalog.
    # Fall back to fetching /v1/models only when no MODEL var is set.
    MODELS_JSON=""
    MODELS_SOURCE=""

    _curated=""
    _curated="$(_curated_models_json)"
    if [ -n "$_curated" ] && [ "$_curated" != "[]" ]; then
        MODELS_JSON="$_curated"
        MODELS_SOURCE="curated"
    else
        # Proxy fetch fallback. Use curl -sf so a connection failure returns
        # non-zero; we handle that explicitly (do NOT let set -e kill us).
        _raw=""
        if _raw="$(curl -sf -H "Authorization: Bearer ${AUTH_TOKEN}" \
            "http://localhost:${PORT}/v1/models" 2>/dev/null)"; then
            MODELS_JSON="$(printf '%s' "$_raw" | jq -c '[.data[].id]')"
            if [ -z "$MODELS_JSON" ] || [ "$MODELS_JSON" = "[]" ]; then
                echo "Warning: proxy returned an empty model list."
                MODELS_JSON=""
            else
                MODELS_SOURCE="fetched"
            fi
        else
            echo "Warning: proxy not reachable at http://localhost:${PORT}/v1/models." >&2
            echo "         No MODEL env var set either — writing managed settings" >&2
            echo "         WITHOUT inferenceModels. Set MODEL in ~/.fcc/.env or" >&2
            echo "         re-run setup-gateway.sh once the server is up." >&2
        fi
    fi

    # Build the JSON object using jq -n to guarantee valid escaping.
    if [ -n "$MODELS_JSON" ]; then
        # Shellcheck: MODELS_JSON is a valid JSON array string from jq.
        # We pass it via --argjson so jq parses it as JSON, not a string.
        SETTINGS_JSON="$(jq -n \
            --arg url "$BASE_URL" \
            --arg key "$AUTH_TOKEN" \
            --argjson models "$MODELS_JSON" \
            '{
                inferenceProvider: "gateway",
                inferenceGatewayBaseUrl: $url,
                inferenceGatewayApiKey: $key,
                inferenceGatewayAuthScheme: "bearer",
                inferenceCredentialKind: "static",
                inferenceModels: $models
            }')"
    else
        SETTINGS_JSON="$(jq -n \
            --arg url "$BASE_URL" \
            --arg key "$AUTH_TOKEN" \
            '{
                inferenceProvider: "gateway",
                inferenceGatewayBaseUrl: $url,
                inferenceGatewayApiKey: $key,
                inferenceGatewayAuthScheme: "bearer",
                inferenceCredentialKind: "static"
            }')"
    fi

    # Ensure the managed directory exists, root-owned, mode 0755.
    $_priv install -d -m 0755 -o root -g root "$MANAGED_DIR"

    # Write via a temp file, then install into place with root ownership
    # and 0644 perms.  This guarantees: regular file (not symlink), root-owned,
    # not group-/world-writable.
    _tmpfile=""
    _tmpfile="$(mktemp)"
    printf '%s\n' "$SETTINGS_JSON" > "$_tmpfile"
    $_priv install -m 0644 -o root -g root "$_tmpfile" "$MANAGED_FILE"
    rm -f "$_tmpfile"

    # Summary.
    echo "Gateway wired for Claude Desktop (unofficial)."
    echo "  Base URL:         ${BASE_URL}"
    if [ -n "$MODELS_JSON" ]; then
        _count=""
        _count="$(printf '%s' "$MODELS_JSON" | jq 'length')"
        echo "  Models (${MODELS_SOURCE}):  ${_count}"
    else
        echo "  Models:           none (no MODEL env var and proxy was down)"
    fi
    echo "  Managed file:     ${MANAGED_FILE}"
    echo ""
    echo "In gateway mode the desktop app does not prompt for a claude.ai"
    echo "login — the gateway credential is used instead.  Chat/Cowork tabs"
    echo "requiring a claude.ai identity are unavailable."
    echo ""
    echo "Quit and reopen Claude Desktop for changes to take effect."
    exit 0
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    --check)
        do_check
        ;;
    --unwire)
        do_unwire
        ;;
    --help|-h)
        print_help
        exit 0
        ;;
    "")
        do_write
        ;;
    *)
        echo "Unknown argument: $1" >&2
        echo "" >&2
        print_help
        exit 1
        ;;
esac
