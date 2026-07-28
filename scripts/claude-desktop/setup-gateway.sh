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
# Read ANTHROPIC_AUTH_TOKEN and PORT from ~/.fcc/.env (managed env path).
# Use a small dotenv parser instead of `source` because the file may contain
# unquoted values or comments.  Fall back to defaults.
# ---------------------------------------------------------------------------
FCC_ENV="${HOME}/.fcc/.env"
AUTH_TOKEN="freecc"
PORT="8082"

if [ -f "$FCC_ENV" ]; then
    # Extract KEY=VALUE lines, skip comments and blanks.
    _val=""
    _val="$(grep -E "^PORT=" "$FCC_ENV" 2>/dev/null | tail -1 | sed -E 's/^PORT=//; s/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/' || true)"
    if [ -n "$_val" ]; then
        PORT="$_val"
    fi
    _val=""
    _val="$(grep -E "^ANTHROPIC_AUTH_TOKEN=" "$FCC_ENV" 2>/dev/null | tail -1 | sed -E 's/^ANTHROPIC_AUTH_TOKEN=//; s/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/' || true)"
    if [ -n "$_val" ]; then
        AUTH_TOKEN="$_val"
    fi
fi

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
        if [ "$_stored" = "$BASE_URL" ]; then
            echo "wired: gateway=${BASE_URL}"
            exit 0
        else
            echo "not wired: inferenceGatewayBaseUrl='${_stored}' (expected '${BASE_URL}')"
            exit 1
        fi
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

    # Fetch model IDs from the proxy.  Use curl -sf so a connection failure
    # returns non-zero; we handle that explicitly (do NOT let set -e kill us).
    MODELS_JSON=""
    FETCH_OK=0

    _raw=""
    if _raw="$(curl -sf -H "Authorization: Bearer ${AUTH_TOKEN}" \
        "http://localhost:${PORT}/v1/models" 2>/dev/null)"; then
        FETCH_OK=1
    fi

    if [ "$FETCH_OK" -eq 1 ]; then
        # Validate and extract model IDs as a JSON array string.
        MODELS_JSON="$(printf '%s' "$_raw" | jq -c '[.data[].id]')"
        if [ -z "$MODELS_JSON" ] || [ "$MODELS_JSON" = "[]" ]; then
            echo "Warning: proxy returned an empty model list."
            MODELS_JSON=""
        fi
    else
        echo "Warning: proxy not reachable at http://localhost:${PORT}/v1/models." >&2
        echo "         Writing managed settings WITHOUT inferenceModels." >&2
        echo "         Re-run setup-gateway.sh once the server is up to populate" >&2
        echo "         the full model list." >&2
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
        echo "  Models fetched:   ${_count}"
    else
        echo "  Models:           none (proxy was down — re-run to populate)"
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
