#!/bin/bash
# ==============================================================================
# setup-gateway.sh — Wire Claude Desktop into the Claude Unbound proxy gateway
# via managed MDM settings.
#
# Supports three Claude Desktop variants:
#
#   1. macOS (official) — Anthropic's Claude.app, installed via `brew install
#      --cask claude` or downloaded from claude.ai.  Managed settings path:
#      /Library/Application Support/Claude/managed-settings.json
#
#   2. Linux (official beta) — Anthropic's Claude Desktop beta, packaged as a
#      .deb for Ubuntu/Debian.  Managed settings path:
#      /etc/claude/managed-settings.json
#
#   3. Linux (unofficial) — aaddrick/claude-desktop-debian, binary
#      /usr/bin/claude-desktop-unofficial, StartupWMClass com.anthropic.Claude.
#      Packaged as an RPM for Fedora/RHEL.  Managed settings path:
#      /etc/claude-desktop/managed-settings.json
#
# What this does:
#   Writes the variant-appropriate managed-settings.json so the desktop app
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
# Platform detection:
#   macOS (Darwin)  -> /Library/Application Support/Claude/managed-settings.json
#   Linux unofficial (claude-desktop-unofficial on PATH or existing
#       /etc/claude/managed-settings.json) -> /etc/claude-desktop/managed-settings.json
#   Linux official (default) -> /etc/claude/managed-settings.json
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

# ---------------------------------------------------------------------------
# Sandbox configuration written into managed settings.
#
# Claude Desktop runs Bash commands in a network/filesystem sandbox by
# default, with a network allowlist of only localhost + the inference
# endpoint and the `dangerouslyDisableSandbox` escape hatch disabled by
# policy.  When inference is routed through the local gateway that means
# the sandbox blocks egress to any non-localhost host, so `git push`,
# `gh`, `curl`, `npm`, and WebFetch all fail with a host-not-allowed error.
#
# This gateway-managed setup keeps FILESYSTEM isolation on (so sandboxed
# commands can only write to the project + temp dirs, plus the toolchain
# caches listed below) while opening NETWORK egress to any host.  The
# reason `allowedDomains` must be a catch-all rather than simply empty:
# when a networked command's host is not on the allowlist, Claude Code
# treats the command as "cannot be sandboxed" and falls back to running
# it OUTSIDE the sandbox — which would also drop filesystem isolation
# for that command.  Allowing all hosts keeps networked commands
# sandboxed (filesystem stays restricted) while letting them reach any
# website.
#
#   - filesystem.allowWrite: toolchain caches that live outside the
#     project.  `uv run pytest` syncs deps into ~/.cache/uv and
#     ~/.local/share/uv; npm/pnpm/yarn use ~/.npm / the pnpm store;
#     Playwright/Puppeteer download browsers into ~/.cache.  Without
#     these entries, dependency install and test runs fail under
#     filesystem isolation.  Project-local dirs (.venv/, node_modules/,
#     dist/, .pytest_cache/) are already writable (they're under the
#     working directory).  Reads are unrestricted by default, so
#     importing installed site-packages works wherever the venv lives.
#   - network.allowedDomains: ["*"] — any website reachable, sandboxed.
#   - excludedCommands: `git`/`gh` run OUTSIDE the sandbox so the
#     credential helper can reach the keyring (D-Bus Unix socket) and
#     SSH keys — the sandbox proxy cannot proxy D-Bus.  `git *` matches
#     `git push origin main`; bare `git` covers no-args.
#
# Known caveat: `jest` with `watchman` is sandbox-incompatible (per
# Claude Code docs) — use `jest --no-watchman`.  Add other toolchain
# caches (e.g. ~/.cargo, ~/.gradle) to allowWrite as needed.
# ---------------------------------------------------------------------------
SANDBOX_JSON='{"enabled":true,"filesystem":{"allowWrite":["~/.cache/uv","~/.local/share/uv","~/.cache/pip","~/.npm","~/.local/share/pnpm","~/.pnpm-store","~/.cache/yarn","~/.yarn","~/.cache/ms-playwright","~/.cache/puppeteer"]},"network":{"allowedDomains":["*"]},"excludedCommands":["git","git *","gh","gh *"]}'

# ---------------------------------------------------------------------------
# Resolve the managed-settings directory based on platform / variant.
#   macOS (Darwin)         -> /Library/Application Support/Claude
#   Linux unofficial        -> /etc/claude-desktop (backward compat)
#   Linux official (default) -> /etc/claude
#
# Override: CLAUDE_DESKTOP_VARIANT=unofficial|official|macos
# ---------------------------------------------------------------------------
resolve_managed_dir() {
    # Explicit override takes priority.
    case "${CLAUDE_DESKTOP_VARIANT:-}" in
        unofficial) printf '/etc/claude-desktop\n'; return 0 ;;
        official)   printf '/etc/claude\n'; return 0 ;;
        macos)      printf '/Library/Application Support/Claude\n'; return 0 ;;
    esac

    local os
    os="$(uname -s)"

    case "$os" in
        Darwin)
            printf '/Library/Application Support/Claude\n'
            ;;
        Linux)
            # If the unofficial binary is on PATH or the legacy directory
            # already exists, keep using it for backward compatibility.
            if command -v claude-desktop-unofficial >/dev/null 2>&1 \
                    || [ -d /etc/claude-desktop ]; then
                printf '/etc/claude-desktop\n'
            else
                printf '/etc/claude\n'
            fi
            ;;
        *)
            # Unknown OS — default to the Linux official path.
            printf '/etc/claude\n'
            ;;
    esac
}

MANAGED_DIR="$(resolve_managed_dir)"
MANAGED_FILE="${MANAGED_DIR}/managed-settings.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

print_help() {
    cat <<EOF
setup-gateway.sh — Wire Claude Desktop into the Claude Unbound proxy.

Supports three variants (auto-detected):
  macOS (official)           /Library/Application Support/Claude/managed-settings.json
  Linux (official beta)      /etc/claude/managed-settings.json
  Linux (unofficial, Fedora)  /etc/claude-desktop/managed-settings.json

Usage:
  setup-gateway.sh            Write or refresh the managed settings file
                              so the desktop app routes through the gateway.
  setup-gateway.sh --check    Exit 0 if the gateway is wired, 1 otherwise.
  setup-gateway.sh --unwire   Remove the managed settings file (revert to
                              default Anthropic login + editable 3P form).
  setup-gateway.sh --help     Show this help.

Environment:
  ANTHROPIC_AUTH_TOKEN        Proxy auth token (read from ~/.fcc/.env,
                              falls back to "freecc").
  PORT                        Proxy port (read from ~/.fcc/.env, "8082").
  CLAUDE_DESKTOP_VARIANT      Override variant detection. Values:
                                unofficial  -> /etc/claude-desktop/...
                                official    -> /etc/claude/... (Linux)
                                macos       -> /Library/Application Support/Claude/...

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
    echo "Claude Desktop reverts to default Anthropic login + editable settings form."
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

    # Privilege elevation is required to write the managed settings file.
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
            --argjson sandbox "$SANDBOX_JSON" \
            '{
                inferenceProvider: "gateway",
                inferenceGatewayBaseUrl: $url,
                inferenceGatewayApiKey: $key,
                inferenceGatewayAuthScheme: "bearer",
                inferenceCredentialKind: "static",
                inferenceModels: $models,
                sandbox: $sandbox
            }')"
    else
        SETTINGS_JSON="$(jq -n \
            --arg url "$BASE_URL" \
            --arg key "$AUTH_TOKEN" \
            --argjson sandbox "$SANDBOX_JSON" \
            '{
                inferenceProvider: "gateway",
                inferenceGatewayBaseUrl: $url,
                inferenceGatewayApiKey: $key,
                inferenceGatewayAuthScheme: "bearer",
                inferenceCredentialKind: "static",
                sandbox: $sandbox
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
    echo "Gateway wired for Claude Desktop (${MANAGED_DIR})."
    echo "  Base URL:         ${BASE_URL}"
    if [ -n "$MODELS_JSON" ]; then
        _count=""
        _count="$(printf '%s' "$MODELS_JSON" | jq 'length')"
        echo "  Models fetched:   ${_count}"
    else
        echo "  Models:           none (proxy was down — re-run to populate)"
    fi
    echo "  Managed file:     ${MANAGED_FILE}"
    echo "  Sandbox:          fs isolated, network *, git/gh excluded"
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
