#!/usr/bin/env bash
# Start the MCP meta-router stack:
#   - one supergateway per stdio backend (stdio -> http://127.0.0.1:PORT/sse)
#   - socat bridging a Unix socket to the meta-router's stdio
#
# Lifecycle: this script is meant to be the *first command* in a dedicated
# kitty tab opened by launcher.sh. When that tab (or the whole kitty
# window) closes, the tab's process group is killed and this script + all
# children die with it. Nothing is enabled at boot; nothing persists.
#
# Implementation note: supergateway uses `child_process.spawn(stdioCmd,
# { shell: true })` internally — it hands the --stdio value to /bin/sh.
# Passing a multi-word command string here causes shell-mangling on some
# setups (the command ends up being prefixed with `uv `). We side-step
# that by writing a one-line wrapper script per backend that exports
# the env vars and `exec`s the real command, and pass the wrapper's path
# as --stdio. The shell then runs a single, unambiguous filename.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${MCP_CONFIG:-$HOME/.fcc/mcp_config.json}"
STOP_SCRIPT="$SCRIPT_DIR/stop_mcp.sh"

STATE_DIR="$HOME/.mcp-router"
RUN_DIR="$STATE_DIR/run"
LOG_DIR="$STATE_DIR/logs"
SOCK_DIR="$STATE_DIR/sockets"
mkdir -p "$RUN_DIR" "$LOG_DIR" "$SOCK_DIR"

export PATH="$HOME/.local/bin:$PATH"

# -- stop any previous run cleanly ----------------------------------------
bash "$STOP_SCRIPT" --quiet || true

# -- sanity checks --------------------------------------------------------
for cmd in npx socat jq uv; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "FATAL: $cmd not found in PATH" >&2
        exit 1
    fi
done
[ -f "$CONFIG" ] || { echo "FATAL: $CONFIG not found" >&2; exit 1; }

# -- read config ---------------------------------------------------------
# Portable read of JSON array keys (bash 3.2+ / zsh compatible).
# mapfile requires bash 4+ (not available on macOS stock bash 3.2).
#
# Backends live in two registries: `servers` (per-host) and
# `shared_servers` (cross-project, managed by the Admin UI). The
# meta-router activates entries from BOTH, so supergateways must be
# spawned for stdio entries in BOTH. Without this, every `[shared] *`
# stdio backend fails to activate with httpx.ConnectError because
# nothing is listening on its port. We collect (source\tname) pairs so
# the spawn loop can look each entry up in the right registry and give
# shared backends filename-safe slugs (the `[shared] ` router prefix is
# not safe for filenames).
BACKENDS=()
while IFS=$'\t' read -r src name; do
    BACKENDS+=("${src}"$'\t'"${name}")
done < <(jq -r '.servers | keys[] | "servers\t\(.)"' "$CONFIG")
while IFS=$'\t' read -r src name; do
    BACKENDS+=("${src}"$'\t'"${name}")
done < <(jq -r '.shared_servers | keys[] | "shared_servers\t\(.)"' "$CONFIG")

# Slug for per-backend files. Shared backends get a `shared.` prefix so
# their log/pid/env/wrapper files never collide with a same-named entry
# in `servers`.
slug_for() {
    if [ "$1" = "shared_servers" ]; then
        printf 'shared.%s' "$2"
    else
        printf '%s' "$2"
    fi
}

# Echo the npx package spec for a stdio backend, or "" if the backend
# isn't an npx-launched server. The package is the first non-flag token
# in args, or the token right after `-p` (npx's --package flag). Used to
# detect backends that share an npx package — spawning those in
# parallel races npx's cache install (npm ENOTEMPTY) because both
# write the same ~/.npm/_npx/<hash> dir. The first such backend warms
# the cache; siblings wait for it to be healthy before spawning.
npx_pkg_for() {  # <src> <name>
    local src="$1" name="$2"
    [ "$(jq -r ".${src}[\"${name}\"].command" "$CONFIG")" = "npx" ] || return 0
    local tok grab=0
    while IFS= read -r tok; do
        if [ "$grab" = "1" ]; then printf '%s' "$tok"; return 0; fi
        case "$tok" in
            -p) grab=1 ;;
            -*) ;;
            *) printf '%s' "$tok"; return 0 ;;
        esac
    done < <(jq -r ".${src}[\"${name}\"].args[]?" "$CONFIG")
}

declare -A SEEN_PKG=()
SOCKET_PATH=$(jq -r '.router_socket' "$CONFIG")
ROUTER_PIDFILE=$(jq -r '.router_pidfile' "$CONFIG")
ROUTER_LOG=$(jq -r '.router_log' "$CONFIG")
HEALTH_TIMEOUT_S=$(jq -r '.health_timeout_s' "$CONFIG")

# Expand ~/ and literal $HOME in config values. mcp_config.example.json uses
# ~/... so users can copy it as-is, and advanced users sometimes write
# $HOME/... — bash does not perform either expansion inside the quoted
# strings we read from jq, so do it here. Pure string substitution (no
# eval) so a hostile config file can't execute code.
#
# Implementation note: the pattern in `${p#~}` MUST NOT quote the tilde
# here, but the `~` in the case labels is literal because case-label
# globbing does not perform tilde expansion. The earlier form
# `${1#~}` looked correct but the unquoted `~` in the *pattern* position
# undergoes tilde expansion as the pattern itself, so it never matched a
# literal leading `~` and produced "$HOME~/.mcp-router/..." — which then
# crashed mcp_router.py's FileHandler with FileNotFoundError. Keeping the
# tilde in the case label (literal) and stripping it with `${p#~}` (the
# value `p`, not a pattern `~`) is the correct, portable fix.
expand_path() {
    local p="$1"
    local tilde="~"
    case "$p" in
        "~") printf '%s' "$HOME" ;;
        "~/"*) printf '%s' "$HOME${p#$tilde}" ;;
        *) printf '%s' "${p//\$HOME/$HOME}" ;;
    esac
}
SOCKET_PATH=$(expand_path "$SOCKET_PATH")
ROUTER_PIDFILE=$(expand_path "$ROUTER_PIDFILE")
ROUTER_LOG=$(expand_path "$ROUTER_LOG")

# Portable timeout: macOS lacks GNU timeout from coreutils.
# Runs a command with a deadline in seconds. Returns the command's exit
# code, or 124 (matching GNU timeout convention) on deadline expiry.
_timeout() {
    local seconds="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$seconds" "$@"
        return $?
    fi
    # Fallback: run in background, kill after deadline.
    "$@" &
    local pid=$!
    (sleep "$seconds" && kill "$pid" 2>/dev/null) &
    local killer=$!
    wait "$pid" 2>/dev/null
    local rc=$?
    if kill -0 "$killer" 2>/dev/null; then
        # Killer still alive → command finished before deadline.
        kill "$killer" 2>/dev/null
        wait "$killer" 2>/dev/null
        return $rc
    fi
    # Killer already dead → deadline expired and killed the command.
    wait "$killer" 2>/dev/null
    return 124
}

# -- health-check helpers -----------------------------------------------
wait_for_health() {
    local name="$1" port="$2"
    local deadline=$((SECONDS + HEALTH_TIMEOUT_S))
    while [ $SECONDS -lt $deadline ]; do
        if curl --silent --fail --max-time 1 "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# -- start one supergateway per stdio backend -----------------------------
echo "[mcp] configuring supergateways for ${#BACKENDS[@]} backend(s)..."
for entry in "${BACKENDS[@]}"; do
    src="${entry%%$'\t'*}"
    name="${entry#*$'\t'}"
    type=$(jq -r ".${src}[\"${name}\"].type" "$CONFIG")
    port=$(jq -r ".${src}[\"${name}\"].port" "$CONFIG")
    slug=$(slug_for "$src" "$name")
    logfile="$LOG_DIR/${slug}.log"
    pidfile="$RUN_DIR/${slug}.pid"

    if [ "$type" = "sse" ]; then
        echo "[mcp] $name: type=sse, will connect directly to remote $(jq -r ".${src}[\"${name}\"].url" "$CONFIG")"
        # No supergateway needed for remote SSE backends.
        host=$(jq -r ".${src}[\"${name}\"].url" "$CONFIG" | sed -E 's|^https?://||; s|/.*$||; s|:[0-9]+$||')
        if ! _timeout 3 bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
            echo "[mcp]   warn: cannot reach $host:$port (will fail at activation time)"
        fi
        continue
    fi

    if [ "$type" = "http" ]; then
        echo "[mcp] $name: type=http, will connect directly to $(jq -r ".${src}[\"${name}\"].url" "$CONFIG")"
        # No supergateway needed for HTTP Streamable backends.
        continue
    fi

    cmd=$(jq -r ".${src}[\"${name}\"].command" "$CONFIG")
    # Portable read of JSON arrays (bash 3.2+ / zsh compatible).
    ARGS=()
    while IFS= read -r line; do
        ARGS+=("$line")
    done < <(jq -r ".${src}[\"${name}\"].args[]" "$CONFIG")
    ENV_KV=()
    while IFS= read -r line; do
        ENV_KV+=("$line")
    done < <(jq -r ".${src}[\"${name}\"].env // {} | to_entries[] | \"\(.key)=\\(.value)\"" "$CONFIG")

    # Write env vars to a separate file (no shell-quoting needed) and a
    # wrapper script that sources it then execs the real command. The
    # wrapper is a single, unambiguous path — supergateway's shell
    # invocation never has to parse a multi-word command.
    envfile="$RUN_DIR/${slug}.env"
    wrapper="$RUN_DIR/${slug}.sh"
    {
        echo "# Auto-generated env file for $name"
        printf 'export %q\n' "${ENV_KV[@]}"
    } > "$envfile"
    chmod 600 "$envfile"
    {
        echo "#!/usr/bin/env bash"
        echo "# Auto-generated by start_mcp.sh — do not edit."
        echo "source '${envfile}'"
        printf 'exec %q' "$cmd"
        for arg in "${ARGS[@]}"; do
            printf ' %q' "$arg"
        done
        echo
    } > "$wrapper"
    chmod 700 "$wrapper"

    echo "[mcp] $name: spawning supergateway on port $port (env: ${#ENV_KV[@]} var(s))"
    # If a sibling backend already started with the same npx package,
    # wait for it to be healthy first. Its npx install will have
    # completed and cached the package in ~/.npm/_npx/, so this backend's
    # `npx -y <pkg>@latest` reuses the cache instead of racing the same
    # cache dir (npm ENOTEMPTY, which crashes the child MCP server).
    pkgkey=$(npx_pkg_for "$src" "$name")
    if [ -n "$pkgkey" ] && [ -n "${SEEN_PKG[$pkgkey]:-}" ]; then
        wait_for_health "sibling $pkgkey for $name" "${SEEN_PKG[$pkgkey]}" || true
    fi
    [ -n "$pkgkey" ] && SEEN_PKG[$pkgkey]=$port
    (
        cd "$HOME"
        npx -y supergateway \
            --stdio "$wrapper" \
            --port "$port" \
            --baseUrl "http://127.0.0.1:$port" \
            --logLevel info \
            --healthEndpoint "/healthz" \
            >"$logfile" 2>&1 &
        echo $! > "$pidfile"
    )
done

# -- health-check the stdio supergateways ---------------------------------
echo "[mcp] waiting up to ${HEALTH_TIMEOUT_S}s for supergateways to be healthy..."
fails=()
for entry in "${BACKENDS[@]}"; do
    src="${entry%%$'\t'*}"
    name="${entry#*$'\t'}"
    type=$(jq -r ".${src}[\"${name}\"].type" "$CONFIG")
    if [ "$type" = "sse" ] || [ "$type" = "http" ]; then continue; fi
    port=$(jq -r ".${src}[\"${name}\"].port" "$CONFIG")
    if ! wait_for_health "$name" "$port"; then
        fails+=("$name:$port")
    fi
done
if [ ${#fails[@]} -ne 0 ]; then
    echo "[mcp] FATAL: supergateways not healthy after ${HEALTH_TIMEOUT_S}s: ${fails[*]}" >&2
    echo "[mcp] check logs: $LOG_DIR/<name>.log" >&2
    for entry in "${BACKENDS[@]}"; do
        src="${entry%%$'\t'*}"
        name="${entry#*$'\t'}"
        type=$(jq -r ".${src}[\"${name}\"].type" "$CONFIG")
        if [ "$type" = "sse" ] || [ "$type" = "http" ]; then continue; fi
        slug=$(slug_for "$src" "$name")
        echo "[mcp]   --- $name log tail ---" >&2
        tail -n 20 "$LOG_DIR/${slug}.log" >&2 || true
    done
    bash "$STOP_SCRIPT" --quiet || true
    exit 1
fi

# -- start socat bridge to meta-router -----------------------------------
rm -f "$SOCKET_PATH"

echo "[mcp] starting meta-router daemon at $SOCKET_PATH"
# The meta-router is now a persistent Unix-socket daemon. One process
# handles all client connections — no per-connection fork, no per-
# connection uv-run / import overhead. start_mcp.sh stays in `wait`
# below so the tab stays alive; the tab's process group is killed when
# it closes, which terminates the meta-router and the supergateways.
cd "$SCRIPT_DIR"
uv run --directory "$SCRIPT_DIR" \
    python mcp_router.py \
    --config "$CONFIG" \
    --socket "$SOCKET_PATH" \
    --log "$ROUTER_LOG" \
    >"$LOG_DIR/router-stdout.log" 2>&1 &
ROUTER_PID=$!
echo "$ROUTER_PID" > "$RUN_DIR/router.pid"
cd "$HOME"

# Wait for the meta-router to bind the socket (it imports MCP SDK + creates
# listeners, so allow a few seconds).
for ((i = 1; i <= 30; i++)); do
    if [ -S "$SOCKET_PATH" ] && kill -0 "$ROUTER_PID" 2>/dev/null; then
        break
    fi
    sleep 0.5
done
if [ ! -S "$SOCKET_PATH" ]; then
    echo "[mcp] FATAL: meta-router did not create $SOCKET_PATH" >&2
    tail -n 30 "$LOG_DIR/router-stdout.log" >&2 || true
    bash "$STOP_SCRIPT" --quiet || true
    exit 1
fi

echo
echo "[mcp] ✅ ready."
echo "[mcp]    meta-router socket:  $SOCKET_PATH"
echo "[mcp]    supergateways:        $(for entry in "${BACKENDS[@]}"; do printf '%s, ' "${entry#*$'\t'}"; done | sed 's/, $//')"
echo "[mcp]    logs:                $LOG_DIR"
echo "[mcp]    stop with:           $STOP_SCRIPT"
echo "[mcp]    (or just close this kitty tab)"
echo

# -- post-startup self-test ------------------------------------------------
# Run the end-to-end test against the just-started daemon to catch SDK or
# router regressions that would otherwise silently surface as "tools fetch
# failed" in fcc-claude. The test connects, sends initialize + tools/list
# (the same path mcp-proxy-tool uses), and asserts all 4 control tools
# come back. Failure here tears the stack down so the launcher exits
# loudly instead of handing the user a broken MCP.
echo "[mcp] running post-startup self-test..."
if ! uv run --directory "$SCRIPT_DIR" \
        python _test_e2e.py --self-test-only --socket "$SOCKET_PATH"; then
    echo "[mcp] FATAL: post-startup self-test failed; tearing down." >&2
    echo "[mcp] --- last 40 lines of router log ---" >&2
    tail -n 40 "$ROUTER_LOG" >&2 || true
    bash "$STOP_SCRIPT" --quiet || true
    exit 1
fi
echo "[mcp] ✅ self-test passed at $(date -u '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || date -u '+%Y-%m-%dT%H:%M:%S') (socket=$SOCKET_PATH)."
echo

# Stay in foreground so the tab stays alive. We block on the meta-
# router's PID (a direct child of this shell). When the meta-router
# dies — or when the tab closes and SIGHUPs us — this script exits,
# the tab's process group is killed, and all supergateways die with it.
wait "$ROUTER_PID"
