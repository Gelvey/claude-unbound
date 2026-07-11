#!/bin/bash
# Claude Unbound Launcher (macOS / Linux, kitty edition)
#
# Opens a kitty window with 3 tabs: MCP Router, Claude Unbound Server, Claude Unbound CLI.
# Runs a preflight sync / auto-update check before opening the main
# tabs. No patch overlay needed — the fork has all
# customisations merged directly.
#
# Requires: kitty, uv, git, kitten (ships with kitty)

REPO_DIR="$HOME/claude-unbound"
# Override with FCC_FORK_URL=<url> to track a different remote.
# Default points to the publicly-published claude-unbound fork.
FORK_URL="${FCC_FORK_URL:-https://github.com/Gelvey/claude-unbound}"
SOCKET="${XDG_RUNTIME_DIR:-/tmp}/fcc-kitty-$$-$(date +%s%N 2>/dev/null || date +%s).sock"

# ── Per-tab colour palette (active / inactive) ──────────────────────────────
# Server=blue, MCP Router=green, Claude Code=orange. Applied after each
# spawn via color_tab() (matched by title); kitty @ launch is synchronous so
# the title match is race-free.
SERVER_ACTIVE_BG="#2f6fbd";   SERVER_ACTIVE_FG="#ffffff"
SERVER_INACTIVE_BG="#16314f";  SERVER_INACTIVE_FG="#6f9fd6"
ROUTER_ACTIVE_BG="#3a9c4e";    ROUTER_ACTIVE_FG="#ffffff"
ROUTER_INACTIVE_BG="#14331c";  ROUTER_INACTIVE_FG="#5fbf73"
CLAUDE_ACTIVE_BG="#e08a2b";    CLAUDE_ACTIVE_FG="#1a1205"
CLAUDE_INACTIVE_BG="#3a2410";  CLAUDE_INACTIVE_FG="#e0a85f"

# Colour a tab in the main kitty window by title.
# Args: title  active_bg active_fg inactive_bg inactive_fg
color_tab() {
    kitten @ --to "unix:$SOCKET" set-tab-color \
        --match "title:^$1\$" \
        "active_bg=$2" "active_fg=$3" \
        "inactive_bg=$4" "inactive_fg=$5" \
        2>/dev/null || true
}

# ── Portable helpers (macOS + Linux) ─────────────────────────────────────────
# Desktop notification: Linux uses notify-send, macOS uses osascript.
# pgrep -x Finder guards against headless macOS (CI, servers) where
# osascript hangs without a window server.
notify() {
    local urgency="$1" title="$2" body="$3"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -u "$urgency" "$title" "$body"
    elif command -v osascript >/dev/null 2>&1 && pgrep -x Finder >/dev/null; then
        # Escape double-quotes and backslashes for AppleScript string literals.
        local escaped_title escaped_body
        escaped_title=$(printf '%s' "$title" | sed 's/\\/\\\\/g; s/"/\\"/g')
        escaped_body=$(printf '%s' "$body" | sed 's/\\/\\\\/g; s/"/\\"/g')
        osascript -e "display notification \"${escaped_body}\" with title \"${escaped_title}\""
    else
        echo "[$title] $body" >&2
    fi
}

# Bring a window to the front by title.
activate_window() {
    if command -v wmctrl >/dev/null 2>&1; then
        wmctrl -a "$1" 2>/dev/null
    elif command -v xdotool >/dev/null 2>&1; then
        xdotool search --name "$1" windowactivate 2>/dev/null
    elif command -v osascript >/dev/null 2>&1; then
        osascript -e "tell application \"kitty\" to activate" 2>/dev/null
    fi
}

# ── Dependency check (kitty only — needed for preflight window) ─────────────
if ! command -v kitty &> /dev/null; then
    notify critical "Claude Unbound" "Error: 'kitty' is not installed"
    exit 1
fi

# ── Make sure the repo is cloned ──────────────────────────────────────────────
if [ ! -d "$REPO_DIR" ]; then
    git clone "$FORK_URL" "$REPO_DIR" || {
        notify critical "Claude Unbound" "Failed to clone repository"
        exit 1
    }
fi

# ── Preflight sync check ─────────────────────────────────────────────────────
# Fetches origin, shows recent commits, and offers a force-pull before opening
# the main kitty window. The preflight runs in its own dedicated kitty window
# (blocking on the kitty PID) so the prompt is always interactive — even when
# launcher.sh was invoked outside a terminal.
PREFLIGHT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/fcc-preflight.XXXXXX") || {
    notify critical "Claude Unbound" "Failed to create preflight temp directory"
    exit 1
}
PREFLIGHT_SCRIPT="$PREFLIGHT_DIR/preflight.sh"
cat > "$PREFLIGHT_SCRIPT" <<'PREFLIGHT_EOF'
#!/bin/bash
REPO_DIR="$HOME/claude-unbound"
cd "$REPO_DIR" || exit 1

echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║        Claude Unbound — Preflight Sync Check             ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo ""

if ! git remote get-url origin >/dev/null 2>&1; then
    echo "[fcc] No origin remote configured — skipping sync check"
    sleep 2
    exit 0
fi

ORIGIN_URL=$(git remote get-url origin)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")

echo "  Remote : $ORIGIN_URL"
echo "  Branch : $CURRENT_BRANCH"
echo ""

if ! git fetch origin --quiet 2>/dev/null; then
    echo "  ⚠ Could not reach remote — continuing with local checkout"
    sleep 2
    exit 0
fi

LOCAL_HEAD=$(git rev-parse HEAD 2>/dev/null)
REMOTE_HEAD=$(git rev-parse "origin/$CURRENT_BRANCH" 2>/dev/null || git rev-parse origin/main 2>/dev/null)

if [ -n "$LOCAL_HEAD" ] && [ -n "$REMOTE_HEAD" ] && [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
    NEW_COUNT=$(git rev-list --count "$LOCAL_HEAD..$REMOTE_HEAD" 2>/dev/null || echo "?")
    echo "  ⚠ $NEW_COUNT new commit(s) available on remote"
    echo ""

    # Show the last 10 commits on origin
    git log "origin/$CURRENT_BRANCH" --oneline --decorate=short \
        -10 --format="    %C(yellow)%h%C(reset) %C(dim)%ar%C(reset) %s" 2>/dev/null \
        || git log origin/main --oneline --decorate=short \
            -10 --format="    %C(yellow)%h%C(reset) %C(dim)%ar%C(reset) %s" 2>/dev/null
    echo ""

    echo "  ─────────────────────────────────────────────────────────"
    echo "  ⚠  WARNING: Force-pull will DISCARD all local changes"
    echo "     and reset to the remote state."
    echo ""
    printf "  Pull latest state of claude-unbound? [y/N] "
    read -r REPLY
    echo ""

    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        echo "[fcc] Force-pulling latest state from origin..."
        if git reset --hard "origin/$CURRENT_BRANCH" 2>/dev/null \
                || git reset --hard origin/main 2>/dev/null; then
            echo "[fcc] ✓ Local checkout reset to $(git rev-parse --short HEAD)"
        else
            echo "[fcc] ERROR: Force-pull failed"
        fi
    else
        echo "[fcc] Skipping pull — continuing with local checkout"
    fi
else
    echo "  ✓ Local checkout is already up to date"
fi

echo ""
echo "[fcc] Preflight complete — launching Claude Unbound..."
sleep 1
PREFLIGHT_EOF
chmod +x "$PREFLIGHT_SCRIPT"

# Run the preflight. When launcher.sh was invoked from an interactive
# terminal (stdout + stdin are TTYs) we print the preflight directly to
# stdout, matching the original behaviour. When invoked from a non-terminal
# context (e.g. a .desktop shortcut) the prompt would otherwise be lost,
# so we open a dedicated kitty window that runs the preflight script and
# `wait` for the user to dismiss it before the main tabs can open.
if [ -t 1 ] && [ -t 0 ]; then
    if ! bash "$PREFLIGHT_SCRIPT"; then
        echo "[fcc] WARNING: preflight sync check failed, continuing with local checkout" >&2
    fi
else
    PREFLIGHT_SOCKET="${XDG_RUNTIME_DIR:-/tmp}/fcc-preflight-kitty-$$-$(date +%s%N 2>/dev/null || date +%s).sock"

    kitty \
        --config NONE \
        --listen-on "unix:$PREFLIGHT_SOCKET" \
        --override "allow_remote_control=socket-only" \
        --title "Claude Unbound — Preflight" \
        bash -c "$PREFLIGHT_SCRIPT; printf '\nPress any key to launch Claude Unbound... '; read -rn 1; exit 0" &

    PREFLIGHT_KITTY_PID=$!
    sleep 0.5
    if ! kill -0 "$PREFLIGHT_KITTY_PID" 2>/dev/null; then
        notify critical "Claude Unbound" "Pre-flight kitty window failed to start"
        rm -rf "$PREFLIGHT_DIR"
        exit 1
    fi

    # The inner bash exits via `exit 0` once the user presses a key (success
    # path) or via non-zero if the window crashed. Treat any non-zero wait
    # result as a non-fatal warning so the main tabs still launch.
    wait "$PREFLIGHT_KITTY_PID" 2>/dev/null || {
        if [ -t 2 ]; then
            echo "[fcc] WARNING: preflight sync check did not complete cleanly, continuing with local checkout" >&2
        fi
        notify critical "Claude Unbound" "Pre-flight sync check did not complete cleanly — continuing"
    }
fi
rm -rf "$PREFLIGHT_DIR"

# ── Dependency check (remaining deps — after preflight) ──────────────────────
# fcc-server and fcc-claude are launched via `uv run` from the repo so the
# latest source is always used — only `uv` and `git` need to be on PATH.
for cmd in uv git; do
    if ! command -v "$cmd" &> /dev/null; then
        notify critical "Claude Unbound" "Error: '$cmd' is not installed"
        exit 1
    fi
done

# MCP stack dependencies (only required if the user is using the meta-router)
MCP_SCRIPT="$REPO_DIR/scripts/mcp/start_mcp.sh"
if [ -x "$MCP_SCRIPT" ]; then
    for cmd in npx socat jq uv; do
        if ! command -v "$cmd" &> /dev/null; then
            notify critical "Claude Unbound" "MCP stack enabled but '$cmd' is not installed"
            exit 1
        fi
    done
fi

cd "$REPO_DIR" || {
    notify critical "Claude Unbound" "Cannot cd to $REPO_DIR"
    exit 1
}

# ── Ensure ~/.fcc/mcp_config.json exists ──────────────────────────────────────
MCP_CONFIG_FILE="$HOME/.fcc/mcp_config.json"
MCP_CONFIG_EXAMPLE="$REPO_DIR/scripts/mcp/mcp_config.example.json"
if [ ! -f "$MCP_CONFIG_FILE" ]; then
    if [ -f "$MCP_CONFIG_EXAMPLE" ]; then
        mkdir -p "$HOME/.fcc"
        cp "$MCP_CONFIG_EXAMPLE" "$MCP_CONFIG_FILE"
        chmod 600 "$MCP_CONFIG_FILE"
        echo "[fcc] WARNING: created $MCP_CONFIG_FILE from example — edit with real secrets before using MCP backends"
        echo "[fcc]   You can edit it by hand or use the Admin UI → MCP Router view"
    fi
fi

# ── Open kitty with the 3 tabs ─────────────────────────────────────────────────
# --config NONE loads no kitty.conf, so the tab bar styling and the
# Ctrl+Shift+T keybinding are injected via --override. Ctrl+Shift+T opens a
# ready, orange, connected Claude Code tab (scripts/kitty/_claude_tab.sh)
# instead of the default bare shell.
kitty \
    --config NONE \
    --listen-on "unix:$SOCKET" \
    --override "allow_remote_control=socket-only" \
    --override "tab_bar_style=powerline" \
    --override "tab_powerline_style=slanted" \
    --override "tab_bar_min_tabs=1" \
    --override "tab_title_max_length=28" \
    --override "active_tab_font_style=bold" \
    --override "tab_separator= " \
    --override "map ctrl+shift>t launch --type=tab --tab-title='Claude Code' --cwd=$REPO_DIR bash $REPO_DIR/scripts/kitty/_claude_tab.sh" \
    --title "Claude Unbound" \
    bash -c "echo '=== Claude Unbound CLI (waiting ${FCC_CLIENT_WARMUP_S:-5}s for fcc-server) ===' && sleep ${FCC_CLIENT_WARMUP_S:-5} && uv run fcc-claude; exec bash" &

KITTY_PID=$!
sleep 1
if ! kill -0 "$KITTY_PID" 2>/dev/null; then
    notify critical "Claude Unbound" "kitty failed to start"
    exit 1
fi

# Colour the first tab (the Claude Unbound CLI tab, titled "Claude Unbound")
# orange. The fcc-claude session is interactive here too.
color_tab "Claude Unbound" \
    "$CLAUDE_ACTIVE_BG" "$CLAUDE_ACTIVE_FG" \
    "$CLAUDE_INACTIVE_BG" "$CLAUDE_INACTIVE_FG"

# Spawn the other 2 tabs into the same kitty window
spawn_tab() {
    local title="$1"; shift
    local _err
    _err=$(mktemp 2>/dev/null) || return 1
    if kitten @ --to "unix:$SOCKET" launch --type=tab --tab-title="$title" -- "$@" 2>"$_err"; then
        rm -f "$_err"
    else
        echo "[fcc] WARN: failed to spawn $title tab:"; cat "$_err"; rm -f "$_err"
    fi
}

# Tab 1: MCP Router (only if start_mcp.sh exists and deps are present)
if [ -x "$MCP_SCRIPT" ] && command -v npx >/dev/null 2>&1 \
        && command -v socat >/dev/null 2>&1 \
        && command -v jq >/dev/null 2>&1 \
        && command -v uv >/dev/null 2>&1; then
    spawn_tab "MCP Router" bash -c "
        echo '=== MCP Router ==='
        $MCP_SCRIPT
        rc=\$?
        echo
        echo \"--- start_mcp.sh exited with code \$rc ---\"
        if [ \$rc -ne 0 ]; then
            echo 'ERROR: start_mcp.sh failed. Check ~/.mcp-router/logs/ for details.'
        fi
        exec bash
    "
    color_tab "MCP Router" \
        "$ROUTER_ACTIVE_BG" "$ROUTER_ACTIVE_FG" \
        "$ROUTER_INACTIVE_BG" "$ROUTER_INACTIVE_FG"
else
    echo "[fcc] MCP Router tab skipped (start_mcp.sh missing or deps not on PATH)"
fi

# Tab 2: Claude Unbound Server (run from repo via uv so the latest source is always used)
spawn_tab "Server" bash -c "echo '=== Claude Unbound Server ===' && uv run fcc-server; exec bash"
color_tab "Server" \
    "$SERVER_ACTIVE_BG" "$SERVER_ACTIVE_FG" \
    "$SERVER_INACTIVE_BG" "$SERVER_INACTIVE_FG"

# The first kitty window already has the Claude Unbound CLI tab.

TABS_OPENED=2  # Claude Unbound CLI + Server always open
if [ -x "$MCP_SCRIPT" ] && command -v npx >/dev/null 2>&1 \
        && command -v socat >/dev/null 2>&1 \
        && command -v jq >/dev/null 2>&1 \
        && command -v uv >/dev/null 2>&1; then
    TABS_OPENED=$((TABS_OPENED + 1))
fi

notify normal "Claude Unbound" \
    "$TABS_OPENED tab(s) opened (MCP / Server / Claude)" \
    2>/dev/null || true

activate_window "Claude Unbound" || true

echo "Claude Unbound tabs opened (MCP / Server / Claude)."
exit 0
