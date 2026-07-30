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
# Real home directory — the invoking user's home, even under sudo.
#
# setup-gateway.sh is normally run with `sudo bash ...` because the managed
# settings file must be root-owned. sudo resets $HOME to root's home
# (/root), so reading "$HOME/.fcc/.env" under sudo would read /root/.fcc/.env
# (absent) and the script would emit "no MODEL env var set" and write
# managed settings WITHOUT inferenceModels — leaving the desktop's picker
# to auto-discover official Anthropic + raw gateway models. _real_home
# resolves the invoking user's home via SUDO_USER so the right ~/.fcc/.env
# (and ~/.claude.json) is read regardless of how the script is elevated.
#   _real_home   -> real home dir on stdout (falls back to $HOME)
_real_home() {
    local user="${SUDO_USER:-}"
    if [ -n "$user" ] && [ "$user" != "root" ]; then
        # Linux: getent passwd. macOS: dscl. Both quiet on miss.
        local home
        home="$(getent passwd "$user" 2>/dev/null | cut -d: -f6 || true)"
        if [ -z "$home" ]; then
            home="$(dscl . -read "/Users/$user" NFSHomeDirectory 2>/dev/null \
                | awk '{print $2}' || true)"
        fi
        if [ -n "$home" ]; then
            printf '%s\n' "$home"
            return
        fi
    fi
    printf '%s\n' "${HOME:-/root}"
}

# ---------------------------------------------------------------------------
# Dotenv helpers — read KEY=VALUE from ~/.fcc/.env without `source`, since the
# file may contain unquoted values or comments. Defined before first use so the
# top-level env-reading below can reuse them.
#   _env_val <key> [env_file]   -> value on stdout (empty if missing)
# ---------------------------------------------------------------------------
FCC_ENV="$(_real_home)/.fcc/.env"

_env_val() {
    local key="$1"
    local file="${2:-$FCC_ENV}"
    [ -f "$file" ] || return 0
    grep -E "^${key}=" "$file" 2>/dev/null | tail -1 \
        | sed -E "s/^${key}=//; s/^\"(.*)\"$/\1/; s/^'(.*)'$/\1/" || true
}

# Build a deduped, ordered JSON array of Anthropic-family model routes for
# the Claude Desktop inferenceModels picker, from the chat model env vars
# (MODEL, MODEL_OPUS, MODEL_SONNET, MODEL_HAIKU).
#
# The desktop's managed-settings validator rejects gateway model IDs that
# don't reference an Anthropic model — it requires a bare "claude-*" id or a
# "anthropic/claude-*" gateway route. A raw ref like
# "anthropic/open_router/deepseek/deepseek-v4-flash" is rejected because the
# path after "anthropic/" is not a claude-* model. So we emit Anthropic-family
# routes instead of the raw provider/model refs.
#
# The gateway (fcc-server) routes these by family tier via
# Settings.resolve_model(): a route whose name contains "opus"/"sonnet"/
# "haiku" maps to MODEL_OPUS/MODEL_SONNET/MODEL_HAIKU, and any other name
# falls back to MODEL. So:
#   MODEL (default) -> "anthropic/claude-default"  (no tier substring -> default)
#   MODEL_OPUS      -> "anthropic/claude-opus-4-20250514"
#   MODEL_SONNET    -> "anthropic/claude-sonnet-4-20250514"
#   MODEL_HAIKU     -> "anthropic/claude-haiku-4-20250514"
# The opus/sonnet/haiku suffixes reuse real Anthropic model IDs (matching
# SUPPORTED_CLAUDE_MODELS in api/model_catalog.py) so they route correctly
# and are unambiguous. The date stamp in each id is hidden from the picker
# via "labelOverride" (clean "Claude Unbound" family names); only the
# "name" routes, so the backend is untouched. MODEL is emitted first because
# the desktop treats the first inferenceModels entry as its default
# selection. Entries pointing at the same underlying ref are deduped (first
# wins) so the picker never shows two routes to the same model. Emits a
# compact JSON array on stdout, or nothing if MODEL is absent/empty (the
# caller then omits inferenceModels entirely rather than emit invalid raw
# refs the desktop validator would reject). Args: [env_file]
_curated_models_json() {
    local file="${1:-$FCC_ENV}"
    local model opus sonnet haiku
    model="$(_env_val MODEL "$file")"
    opus="$(_env_val MODEL_OPUS "$file")"
    sonnet="$(_env_val MODEL_SONNET "$file")"
    haiku="$(_env_val MODEL_HAIKU "$file")"

    # Without the default model the curated list is not meaningful.
    [ -n "$model" ] || return 0

    # Emit "<name>\t<label>\t<ref>" triples and dedup by the underlying ref
    # ($3), so two tiers pointing at the same model only appear once (first
    # wins). Each entry is an object: "name" is the routing id (unchanged —
    # the gateway routes by the opus/sonnet/haiku substring in it) and
    # "labelOverride" is the clean picker label that hides the date stamp.
    {
        printf 'anthropic/claude-default\tClaude Unbound Default\t%s\n' "$model"
        [ -n "$opus" ]   && printf 'anthropic/claude-opus-4-20250514\tClaude Opus Unbound\t%s\n' "$opus"
        [ -n "$sonnet" ] && printf 'anthropic/claude-sonnet-4-20250514\tClaude Sonnet Unbound\t%s\n' "$sonnet"
        [ -n "$haiku" ]  && printf 'anthropic/claude-haiku-4-20250514\tClaude Haiku Unbound\t%s\n' "$haiku"
    } | awk -F'\t' '!seen[$3]++' \
      | jq -R -s -c '
          split("\n") | map(select(length > 0)) | map(split("\t"))
          | map({name: .[0], labelOverride: .[1]})
        '
}

# Build a managedMcpServers JSON array mirroring the user-scoped MCP servers
# configured for the Claude Code CLI (~/.claude.json top-level "mcpServers"),
# converted to the desktop's managedMcpServers schema (an array of objects
# with "name" + "transport" + connection fields). The 3P desktop reads MCP
# servers from managedMcpServers in managed-settings.json — it does NOT pick
# up ~/.claude.json mcpServers like the official app's Code tab does — so we
# replicate them here to keep the CLI and desktop in sync. Drops entries
# whose transport the desktop doesn't support (e.g. "ws"). Emits a compact
# JSON array on stdout, or nothing if ~/.claude.json has no mcpServers.
# Args: [claude_json_path]
_managed_mcp_servers_json() {
    local claude_json="${1:-$(_real_home)/.claude.json}"
    [ -f "$claude_json" ] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    jq '
      [ (.mcpServers // {}) | to_entries[] |
        {
          name: .key,
          transport: (.value.type // "stdio"),
          command: .value.command,
          args: .value.args,
          env: .value.env,
          url: .value.url,
          headers: .value.headers
        }
        | with_entries(select(.value != null))
        | if .transport == "streamable-http" then .transport = "http" else . end
        | select(.transport == "stdio" or .transport == "http" or .transport == "sse")
      ]
    ' "$claude_json" 2>/dev/null
}

# Defaults; overridden from ~/.fcc/.env below.
AUTH_TOKEN="freecc"
PORT="8082"

_val="$(_env_val PORT)";        [ -n "$_val" ] && PORT="$_val"
_val="$(_env_val ANTHROPIC_AUTH_TOKEN)"; [ -n "$_val" ] && AUTH_TOKEN="$_val"

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
#     (Covers Bash subprocess egress only. WebFetch / WebSearch — the tools
#     used for web research — are gated by permission rules, not the sandbox;
#     see the PERMS_JSON block below.)
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
# Web-research permissions (WebFetch / WebSearch).
#
# Web research is NOT governed by the Bash sandbox above — the sandbox's
# network.allowedDomains only covers Bash subprocess egress. The WebFetch
# and WebSearch tools are built-in tools that fetch URLs / search the web
# under their own permission boundary, independent of the sandbox. So even
# with network.allowedDomains:["*"], the desktop cannot visit websites for
# research unless a permission rule allows it.
#
# To make web research work by default (without prompting on every fetch),
# we emit a managed permissions.allow list:
#   WebFetch(domain:*)  — allow fetching any URL. The docs state
#                        WebFetch(domain:*) "matches every domain and is
#                        equivalent to a bare WebFetch rule."
#   WebSearch           — allow web search.
# Managed-settings permissions.allow is honored without a workspace trust
# dialog (the file is root-owned/trusted), so this works on first launch.
# Deny/ask rules elsewhere still take precedence (deny-first), but we emit
# only an allow list here.
# ---------------------------------------------------------------------------
PERMS_JSON='{"allow":["WebFetch(domain:*)","WebSearch"]}'

# ---------------------------------------------------------------------------
# Desktop tool egress — coworkEgressAllowedHosts.
#
# IMPORTANT: the Claude Desktop app does NOT honor the `sandbox` key above
# (that's a Claude Code CLI managed-settings feature). The desktop's Cowork
# and Code tabs gate tool egress (Bash, git, gh, npm, pip, WebFetch, ...) via
# a top-level `coworkEgressAllowedHosts` array. Per the desktop configuration
# reference: "When unset, only the inference endpoint is reachable from the
# sandbox; the agent's package installs (pip/npm) and web fetches will fail
# with a 403." That 403 is exactly what blocked `git push` to GitHub even
# though sandbox.network.allowedDomains was ["*"].
#
# The desktop ignores excludedCommands too (a CLI-only field), so git/gh
# cannot be exempted individually — egress must be opened via this list.
# It accepts "*" (allow all), exact hostnames (api.github.com), and
# wildcards (*.corp.com). IP literals and localhost always resolve.
# Web Search is NOT gated by this list (it runs server-side at the
# inference provider); WebFetch IS gated by it.
#
# We set ["*"] so the desktop can reach GitHub (git push, gh), package
# registries (npm, pip), and any website for research — matching the
# "network open" intent of the sandbox block above for CLI sessions.
# ---------------------------------------------------------------------------
EGRESS_JSON='["*"]'

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
  - MCP servers configured for the Claude Code CLI in ~/.claude.json
    (top-level "mcpServers") are mirrored into the desktop's
    "managedMcpServers" so both surfaces see the same servers. Re-run
    setup-gateway.sh after adding/removing CLI MCP servers to resync.
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
            # Discovery must be off so the provider's catalog (official
            # Anthropic models, raw gateway refs like open_router/...) can
            # never leak into the picker alongside the curated list.
            if [ "$(jq -r '.modelDiscoveryEnabled // true' "$MANAGED_FILE" 2>/dev/null)" != "false" ]; then
                echo "not wired: modelDiscoveryEnabled not false (would leak non-curated models)"
                exit 1
            fi
        fi

        # Verify the web-research permissions block is present — a stale file
        # missing it means WebFetch/WebSearch would prompt (or fail) on every
        # research fetch. Re-run setup-gateway.sh to refresh.
        _stored_perms=""
        _stored_perms="$(jq -c '.permissions.allow // []' "$MANAGED_FILE" 2>/dev/null || echo "[]")"
        _expected_perms=""
        _expected_perms="$(printf '%s' "$PERMS_JSON" | jq -c '.allow')"
        if [ "$_stored_perms" != "$_expected_perms" ]; then
            echo "not wired: permissions stale (expected WebFetch(*) + WebSearch allowed)"
            exit 1
        fi

        # Verify desktop tool egress — without coworkEgressAllowedHosts the
        # desktop's Cowork/Code tabs only reach the inference endpoint and
        # every other tool egress (git push, gh, npm, pip, WebFetch) fails
        # with HTTP 403. This is the desktop's egress gate (the `sandbox`
        # key above is a CLI-only field the desktop ignores).
        _stored_egress=""
        _stored_egress="$(jq -c '.coworkEgressAllowedHosts // []' "$MANAGED_FILE" 2>/dev/null || echo "[]")"
        if [ "$_stored_egress" != "$EGRESS_JSON" ]; then
            echo "not wired: coworkEgressAllowedHosts stale (expected [\"*\"] for GitHub + research egress)"
            exit 1
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
    # The file MUST remain root-owned: the Claude Desktop trust check rejects
    # a managed-settings.json that is not owned by root (and not group- or
    # world-writable, with a root-owned parent dir), ignoring it and falling
    # back to the default claude.ai login. So we always elevate here and
    # install the file root-owned; the launcher relies on `--check` to skip
    # the write entirely when the gateway is already correctly wired rather
    # than refreshing unprivileged.
    _priv="$(priv_prefix)"
    if [ -z "$_priv" ]; then
        echo "Error: need sudo or pkexec to write under ${MANAGED_DIR}" >&2
        exit 1
    fi

    # Build the model list for the picker from the chat model env vars
    # (MODEL/MODEL_OPUS/MODEL_SONNET/MODEL_HAIKU): it works even when the
    # proxy is down (the launcher runs this script before fcc-server starts)
    # and keeps the picker to the few models the user actually configured
    # instead of the provider's full catalog.
    #
    # We do NOT fall back to fetching /v1/models when MODEL is unset. The
    # desktop's managed-settings validator requires every inferenceModels
    # entry to be an Anthropic-family route ("claude-*" or "anthropic/claude-*");
    # the proxy catalog returns raw provider refs (e.g.
    # "anthropic/open_router/deepseek/deepseek-v4-flash") that the validator
    # rejects with "configured model ... is not an Anthropic model", leaving
    # the desktop in an invalid_config state. So when no MODEL var is set we
    # write managed settings WITHOUT inferenceModels (the desktop falls back
    # to its default model selection) rather than emit invalid routes.
    MODELS_JSON=""
    MODELS_SOURCE=""

    _curated=""
    _curated="$(_curated_models_json)"
    if [ -n "$_curated" ] && [ "$_curated" != "[]" ]; then
        MODELS_JSON="$_curated"
        MODELS_SOURCE="curated"
    else
        echo "Warning: no MODEL env var set — writing managed settings" >&2
        echo "         WITHOUT inferenceModels. The desktop will use its" >&2
        echo "         default model selection. Set MODEL in ~/.fcc/.env" >&2
        echo "         and re-run setup-gateway.sh to populate the picker." >&2
    fi

    # Mirror the CLI's user-scoped MCP servers (~/.claude.json mcpServers)
    # into the desktop's managedMcpServers so the desktop sees the same MCP
    # servers the CLI does.
    MCP_JSON="$(_managed_mcp_servers_json)"

    # Build the JSON object using jq -n to guarantee valid escaping. Start
    # from the base gateway fields, then add inferenceModels and
    # managedMcpServers only when non-empty.
    SETTINGS_JSON="$(jq -n \
        --arg url "$BASE_URL" \
        --arg key "$AUTH_TOKEN" \
        --argjson sandbox "$SANDBOX_JSON" \
        --argjson perms "$PERMS_JSON" \
        --argjson egress "$EGRESS_JSON" \
        '{
            inferenceProvider: "gateway",
            inferenceGatewayBaseUrl: $url,
            inferenceGatewayApiKey: $key,
            inferenceGatewayAuthScheme: "bearer",
            inferenceCredentialKind: "static",
            sandbox: $sandbox,
            permissions: $perms,
            coworkEgressAllowedHosts: $egress
        }')"

    if [ -n "$MODELS_JSON" ]; then
        # Shellcheck: MODELS_JSON is a valid JSON array string from jq.
        # We pass it via --argjson so jq parses it as JSON, not a string.
        # Also disable auto-discovery: inferenceModels overrides the picker,
        # but setting modelDiscoveryEnabled:false makes it explicit and
        # guarantees the provider's model-list endpoint is never queried —
        # so official Anthropic models and raw gateway models (e.g.
        # open_router/...) can never leak into the picker. The docs say
        # discovery skips automatically when inferenceModels is set; this
        # is the belt-and-suspenders form ("turn off ... to use a fixed list").
        SETTINGS_JSON="$(printf '%s' "$SETTINGS_JSON" \
            | jq --argjson models "$MODELS_JSON" \
               '.inferenceModels = $models | .modelDiscoveryEnabled = false')"
    fi

    if [ -n "$MCP_JSON" ] && [ "$MCP_JSON" != "[]" ]; then
        SETTINGS_JSON="$(printf '%s' "$SETTINGS_JSON" \
            | jq --argjson mcp "$MCP_JSON" '.managedMcpServers = $mcp')"
    fi

    # Ensure the managed directory exists, root-owned, mode 0755.
    $_priv install -d -m 0755 -o root -g root "$MANAGED_DIR"

    # Write via a temp file, then install into place with root ownership
    # and 0644 perms.  This guarantees: regular file (not symlink), root-owned,
    # not group-/world-writable.  Root ownership is REQUIRED — the desktop's
    # trust check rejects a user-owned managed-settings.json and falls back
    # to the default claude.ai login.
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
        echo "  Models (${MODELS_SOURCE}):  ${_count}"
    else
        echo "  Models:           none (no MODEL env var set)"
    fi
    if [ -n "$MCP_JSON" ] && [ "$MCP_JSON" != "[]" ]; then
        _mcp_count=""
        _mcp_count="$(printf '%s' "$MCP_JSON" | jq 'length')"
        echo "  MCP servers:      ${_mcp_count} (mirrored from ~/.claude.json)"
    fi
    echo "  Managed file:     ${MANAGED_FILE}"
    echo "  Sandbox:          fs isolated, network *, git/gh excluded"
    echo "  Web research:     WebFetch(*) + WebSearch allowed"
    echo "  Desktop egress:   coworkEgressAllowedHosts [\"*\"] (git push, gh, npm, pip)"
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
