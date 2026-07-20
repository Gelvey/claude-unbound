#!/usr/bin/env bash
# Stop the MCP meta-router stack started by start_mcp.sh
# Idempotent — safe to run when nothing is running.

set -u

QUIET=0
if [ "${1:-}" = "--quiet" ]; then
    QUIET=1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${MCP_CONFIG:-$HOME/.fcc/mcp_config.json}"
STATE_DIR="$HOME/.mcp-router"
RUN_DIR="$STATE_DIR/run"

log() {
    [ $QUIET -eq 1 ] || echo "[stop] $*"
}

# Kill a supergateway by pidfile and reap its children. First arg is the
# slug used for the pidfile filename; second is the display name.
_stop_gateway() {
    local slug="$1" name="$2"
    local pidfile="$RUN_DIR/${slug}.pid"
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log "killing supergateway $name (pid $pid)"
            kill "$pid" 2>/dev/null || true
            # npx may have spawned children; reap process tree.
            # pkill -P is a GNU extension; macOS pkill lacks -P.
            # Use pgrep -P (portable) + kill, with ps fallback.
            if command -v pgrep >/dev/null 2>&1; then
                pgrep -P "$pid" 2>/dev/null | xargs kill 2>/dev/null || true
            elif command -v ps >/dev/null 2>&1; then
                ps -eo pid,ppid 2>/dev/null | awk -v ppid="$pid" '$2==ppid{print $1}' | xargs kill 2>/dev/null || true
            fi
        fi
        rm -f "$pidfile"
    fi
}

if ! command -v jq >/dev/null 2>&1; then
    log "jq not available; skipping config-driven shutdown"
    exit 0
fi
if [ -f "$CONFIG" ]; then
    SERVERS_JSON=$(jq -c '.servers' "$CONFIG")
    SHARED_JSON=$(jq -c '.shared_servers' "$CONFIG")
    SOCKET_PATH=$(jq -r '.router_socket' "$CONFIG")

    # Stop supergateways. start_mcp.sh spawns one per stdio backend in
    # both `servers` and `shared_servers`; shared backends get a
    # `shared.` filename prefix (see slug_for in start_mcp.sh). Iterate
    # both registries so their pidfiles are reaped cleanly. A stray
    # supergateway is still caught by the pkill -f supergateway below.
    for name in $(echo "$SERVERS_JSON" | jq -r 'keys[] // empty'); do
        _stop_gateway "$name" "$name"
    done
    for name in $(echo "$SHARED_JSON" | jq -r 'keys[] // empty'); do
        _stop_gateway "shared.$name" "$name"
    done

    # Stop socat
    socat_pidfile="$RUN_DIR/socat.pid"
    if [ -f "$socat_pidfile" ]; then
        pid=$(cat "$socat_pidfile" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log "killing socat (pid $pid)"
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$socat_pidfile"
    fi

    # Clean up the socket and any orphan meta-router processes
    if [ -n "${SOCKET_PATH:-}" ] && [ -S "$SOCKET_PATH" ]; then
        rm -f "$SOCKET_PATH"
    fi
fi

# Belt and suspenders: kill any stragglers by name
pkill -f "mcp_router.py" 2>/dev/null || true
pkill -f "supergateway"  2>/dev/null || true

log "done."
