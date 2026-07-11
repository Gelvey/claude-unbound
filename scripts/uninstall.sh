#!/bin/sh
set -eu

PACKAGE_NAME="free-claude-code"
FCC_HOME_DIRNAME=".fcc"
FCC_COMMANDS="fcc-server fcc-claude fcc-codex fcc-init free-claude-code"
REPO_DIR="${FCC_REPO_DIR:-$HOME/claude-unbound}"
MCP_ROUTER_DIR="$HOME/.mcp-router"

dry_run=0

show_usage() {
    cat <<'USAGE'
Usage: uninstall.sh [options]

Removes Claude Unbound: wrapper scripts, repository clone, MCP Router state,
and the ~/.fcc/ config directory.
Does not remove uv, Claude Code, Codex, or the uv-managed Python runtime.

Options:
  --dry-run                Print commands without running them.
  --help                   Show this help text.

Environment:
  FCC_REPO_DIR=<path>
      Override the repository directory to remove. Default: ~/claude-unbound.
USAGE
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n==> %s\n' "$1"
}

quote_arg() {
    case "$1" in
        *[!A-Za-z0-9_./:@%+=,-]*|"")
            escaped=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')
            printf '"%s"' "$escaped"
            ;;
        *)
            printf '%s' "$1"
            ;;
    esac
}

print_command() {
    printf '+'
    for arg in "$@"; do
        printf ' '
        quote_arg "$arg"
    done
    printf '\n'
}

run() {
    print_command "$@"
    if [ "$dry_run" -eq 0 ]; then
        "$@"
    fi
}

is_missing_uv_tool_error() {
    normalized=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$normalized" in
        *"not installed"* | *"no tool"* | *"nothing to uninstall"*) return 0 ;;
        *) return 1 ;;
    esac
}

add_path_entry() {
    [ -n "$1" ] || return 0
    case ":$PATH:" in
        *":$1:"*) ;;
        *) PATH="$1:$PATH" ;;
    esac
}

add_uv_to_path() {
    if [ -n "${XDG_BIN_HOME:-}" ]; then
        add_path_entry "$XDG_BIN_HOME"
    fi

    if [ -n "${HOME:-}" ]; then
        add_path_entry "$HOME/.local/bin"
        add_path_entry "$HOME/.cargo/bin"
    fi

    export PATH
}

is_fcc_command_running() {
    command_name=$1

    if command -v pgrep >/dev/null 2>&1; then
        if pgrep -x "$command_name" >/dev/null 2>&1; then
            return 0
        fi
        if pgrep -f "(^|/)${command_name}( |$)" >/dev/null 2>&1; then
            return 0
        fi
        return 1
    fi

    if ps -A -o comm= 2>/dev/null | grep -qx "$command_name"; then
        return 0
    fi

    return 1
}

assert_no_fcc_processes_running() {
    running=""

    for command_name in $FCC_COMMANDS; do
        if is_fcc_command_running "$command_name"; then
            running="${running} ${command_name}"
        fi
    done

    if [ -n "$running" ]; then
        fail "Claude Unbound is still running (${running# }). Stop those processes, then rerun uninstall."
    fi
}

# Remove wrapper scripts from ~/.local/bin/.
remove_wrapper_scripts() {
    local bin_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
    for cmd in $FCC_COMMANDS; do
        local path="$bin_dir/$cmd"
        if [ -f "$path" ] || [ -L "$path" ]; then
            run rm -f "$path"
            printf 'Removed wrapper: %s\n' "$path"
        fi
    done
}

# Remove the old uv tool installation (fallback for pre-existing installs).
uninstall_free_claude_code() {
    add_uv_to_path

    if ! command -v uv >/dev/null 2>&1; then
        printf 'uv not found on PATH; skipping uv tool uninstall.\n'
        return 0
    fi

    print_command uv tool uninstall "$PACKAGE_NAME"
    if [ "$dry_run" -eq 0 ]; then
        if output=$(uv tool uninstall "$PACKAGE_NAME" 2>&1); then
            return 0
        else
            status=$?
        fi
        if is_missing_uv_tool_error "$output"; then
            printf 'Claude Unbound uv tool not installed or already removed; skipping uv tool uninstall.\n'
            return 0
        fi
        if [ -n "$output" ]; then
            printf '%s\n' "$output" >&2
        fi
        fail "uv tool uninstall $PACKAGE_NAME failed with exit code $status; aborting before deleting ~/.fcc."
    fi
}

# Remove MCP Router state directory (~/.mcp-router/).
remove_mcp_router_state() {
    if [ ! -d "$MCP_ROUTER_DIR" ]; then
        printf 'No MCP Router state at %s; skipping.\n' "$MCP_ROUTER_DIR"
        return 0
    fi
    run rm -rf "$MCP_ROUTER_DIR"
    printf 'Removed MCP Router state: %s\n' "$MCP_ROUTER_DIR"
}

# Remove the repository clone. In dev mode, only the symlink is removed
# (the user's working copy is preserved). In clone mode, the entire
# directory is removed after verifying it looks like our repo.
remove_repo_clone() {
    local install_mode_file="$HOME/$FCC_HOME_DIRNAME/.install_mode"
    local install_mode=""
    if [ -f "$install_mode_file" ]; then
        install_mode=$(cat "$install_mode_file" 2>/dev/null || true)
    fi

    if [ "$install_mode" = "dev" ]; then
        # Dev mode: the repo dir is a symlink to the user's working copy.
        # Remove the symlink but NOT the target.
        if [ -L "$REPO_DIR" ]; then
            run rm -f "$REPO_DIR"
            printf 'Removed symlink %s (your working copy is untouched).\n' "$REPO_DIR"
        fi
        return 0
    fi

    if [ ! -d "$REPO_DIR" ]; then
        printf 'No repository at %s; skipping.\n' "$REPO_DIR"
        return 0
    fi

    # Safety: verify it looks like our repo before deleting
    if [ -d "$REPO_DIR/.git" ] && git -C "$REPO_DIR" remote get-url origin 2>/dev/null | grep -q "claude-unbound"; then
        run rm -rf "$REPO_DIR"
        printf 'Removed repository clone: %s\n' "$REPO_DIR"
    else
        printf 'WARNING: %s does not look like a Claude Unbound clone; not removing.\n' "$REPO_DIR"
        printf 'Remove it manually if you are sure.\n'
    fi
}

purge_fcc_home() {
    [ -n "${HOME:-}" ] || fail "HOME is not set; cannot locate ~/.fcc."

    fcc_home="$HOME/$FCC_HOME_DIRNAME"
    if [ ! -e "$fcc_home" ]; then
        printf 'No FCC config directory at %s; skipping purge.\n' "$fcc_home"
        return 0
    fi

    run rm -rf "$fcc_home"
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry-run)
                dry_run=1
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                show_usage >&2
                fail "unknown option: $1"
                ;;
        esac
        shift
    done
}

parse_args "$@"

step "Checking for running Claude Unbound processes"
assert_no_fcc_processes_running

step "Removing wrapper scripts"
remove_wrapper_scripts

step "Removing old uv tool installation (if any)"
uninstall_free_claude_code

step "Removing MCP Router state"
remove_mcp_router_state

step "Removing repository clone"
remove_repo_clone

# Remove the spawn-claude-tab skill installed by install.sh into ~/.claude/skills/.
remove_skill() {
    local dest="$HOME/.claude/skills/spawn-claude-tab"
    if [ ! -d "$dest" ]; then
        printf 'No skill directory at %s; skipping.\n' "$dest"
        return 0
    fi
    run rm -rf "$dest"
    printf 'Removed skill: %s\n' "$dest"
}

step "Removing Claude Code skill"
remove_skill

step "Purging FCC config and data from ~/.fcc"
purge_fcc_home

printf '\nClaude Unbound has been removed.\n'
printf 'uv, Claude Code, Codex, and the uv-managed Python runtime were left installed.\n'
