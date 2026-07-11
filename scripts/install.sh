#!/bin/sh
set -eu

# Install target for Claude Unbound.
# Clones the repo to ~/claude-unbound and creates wrapper scripts in
# ~/.local/bin/ that invoke `uv run` from the live source tree. This
# ensures source changes are picked up immediately without reinstalling.
#
# Can be overridden via FCC_REPO_URL=<https url>. When install.sh is
# executed from inside a git checkout whose `origin` remote is NOT
# Gelvey/claude-unbound, the installer refuses to silently fall back to the
# canonical URL — pass FCC_REPO_URL pointing at the fork that publishes
# the Python package.

DEFAULT_REPO_HTTPS_URL="https://github.com/Gelvey/claude-unbound"
REPO_HTTPS_URL=""
REPO_DIR="${FCC_REPO_DIR:-$HOME/claude-unbound}"
FCC_HOME_DIRNAME=".fcc"

PYTHON_VERSION="3.14.0"
MIN_UV_VERSION="0.11.0"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

dry_run=0
voice_nim=0
voice_local=0
voice_all=0
torch_backend=""

show_usage() {
    cat <<'USAGE'
Usage: install.sh [options]

Installs Claude Code and Codex if missing, installs or updates uv, Python 3.14.0, and Claude Unbound.

Options:
  --voice-nim              Install NVIDIA NIM voice transcription support.
  --voice-local            Install local Whisper voice transcription support.
  --voice-all              Install all voice transcription backends.
  --torch-backend VALUE    Use a uv PyTorch backend, such as cu130. Requires local voice.
  --dry-run                Print commands without running them.
  --help                   Show this help text.

Environment:
  FCC_REPO_URL=<https url>
      Overrides the install source for the Claude Unbound repository.
      Required when running from a non-upstream fork clone (otherwise the
      installer aborts with an error). The git+ prefix is stripped
      automatically for backward compatibility.
  FCC_REPO_DIR=<path>
      Overrides the clone target directory. Default: ~/claude-unbound.
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

run_uv_installer() {
    printf '+ curl -LsSf %s | sh\n' "$UV_INSTALL_URL"
    if [ "$dry_run" -eq 0 ]; then
        command -v curl >/dev/null 2>&1 || fail "curl is required to install uv."
        curl -LsSf "$UV_INSTALL_URL" | sh
    fi
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

require_command() {
    if [ "$dry_run" -eq 0 ] && ! command -v "$1" >/dev/null 2>&1; then
        fail "$1 is required. Install it first, then rerun this installer."
    fi
}

# Resolve the HTTPS clone URL for the Claude Unbound repository.
# Priority (highest first):
#   1. FCC_REPO_URL env override (always wins; strips git+ prefix for
#      backward compatibility).
#   2. Running from inside a git checkout whose `origin` remote is
#      Gelvey/claude-unbound -> use the canonical URL.
#   3. Running from inside a git checkout whose `origin` remote is anything
#      ELSE (i.e. a different fork) -> REFUSE silent fallback. Print a clear
#      error pointing at FCC_REPO_URL so the user does not unknowingly
#      install a different repo's code.
#   4. Not inside a git checkout (e.g. `curl ... | sh`) -> use canonical URL.
resolve_repo_https_url() {
    if [ -n "${FCC_REPO_URL:-}" ]; then
        # Strip git+ prefix if present (backward compat with old FCC_REPO_URL values)
        url="${FCC_REPO_URL#git+}"
        printf '%s\n' "$url"
        return 0
    fi

    # Robust to `curl | sh` invocations where $0 may be a path under /dev
    # or empty. `cd` failures are swallowed and we fall back to ".".
    script_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd || printf '.')

    if command -v git >/dev/null 2>&1 \
        && git -C "$script_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        origin_url=$(git -C "$script_dir" config --get remote.origin.url 2>/dev/null || true)

        if [ -n "$origin_url" ]; then
            case "$origin_url" in
                *"Gelvey/claude-unbound"*)
                    printf '%s\n' "$DEFAULT_REPO_HTTPS_URL"
                    return 0
                    ;;
                *)
                    printf 'error: non-canonical fork clone detected.\n' >&2
                    printf 'error: git origin: %s\n' "$origin_url" >&2
                    printf 'error: refusing to silently fall back to the canonical install URL.\n' >&2
                    printf 'error: re-run with FCC_REPO_URL pointing at the fork that publishes the repo, e.g.\n' >&2
                    printf 'error:   FCC_REPO_URL=https://github.com/YourUser/your-fork sh install.sh\n' >&2
                    return 1
                    ;;
            esac
        fi
    fi

    # No git context: treat as the canonical `curl ... | sh` pipeline.
    printf '%s\n' "$DEFAULT_REPO_HTTPS_URL"
}

# Resolve the actual repository directory. If running from inside a git
# repo, returns that repo's toplevel. Otherwise returns the standard
# clone location.
resolve_repo_dir() {
    script_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd || printf '.')
    if command -v git >/dev/null 2>&1; then
        toplevel=$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null || true)
        if [ -n "$toplevel" ]; then
            printf '%s\n' "$toplevel"
            return 0
        fi
    fi
    # Standard location
    printf '%s\n' "$REPO_DIR"
}

# Check if path $1 is a symlink pointing to path $2.
is_symlink_to() {
    [ -L "$1" ] || return 1
    target=$(readlink "$1" 2>/dev/null) || return 1
    [ "$(cd "$target" && pwd)" = "$(cd "$2" && pwd)" ]
}

current_uv_version() {
    version=$(uv self version --short 2>/dev/null || true)
    if [ -z "$version" ]; then
        version=$(uv --version 2>/dev/null | sed 's/^uv //; s/ .*//' || true)
    fi

    [ -n "$version" ] || return 1
    printf '%s\n' "$version"
}

version_ge() {
    current=${1%%[-+]*}
    minimum=${2%%[-+]*}

    old_ifs=$IFS
    IFS=.
    set -- $current
    current_major=${1:-0}
    current_minor=${2:-0}
    current_patch=${3:-0}
    set -- $minimum
    minimum_major=${1:-0}
    minimum_minor=${2:-0}
    minimum_patch=${3:-0}
    IFS=$old_ifs

    [ "$current_major" -gt "$minimum_major" ] && return 0
    [ "$current_major" -lt "$minimum_major" ] && return 1
    [ "$current_minor" -gt "$minimum_minor" ] && return 0
    [ "$current_minor" -lt "$minimum_minor" ] && return 1
    [ "$current_patch" -ge "$minimum_patch" ]
}

uv_version_satisfies_minimum() {
    version=$(current_uv_version) || return 1
    version_ge "$version" "$MIN_UV_VERSION"
}

validate_uv_version() {
    [ "$dry_run" -eq 1 ] && return 0

    version=$(current_uv_version) || fail "Unable to determine uv version."
    if ! version_ge "$version" "$MIN_UV_VERSION"; then
        fail "uv $MIN_UV_VERSION or newer is required; found uv $version. Upgrade uv with its installer or package manager, then rerun this installer."
    fi
}

uv_self_update_supported() {
    uv self update --dry-run >/dev/null 2>&1
}

uv_installed_by_homebrew() {
    command -v brew >/dev/null 2>&1 && brew list --versions uv >/dev/null 2>&1
}

uv_installed_by_pipx() {
    command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -Eq '(^|[[:space:]])package uv([[:space:]]|$)'
}

uv_installed_in_active_virtualenv() {
    [ -n "${VIRTUAL_ENV:-}" ] || return 1

    uv_path=$(command -v uv)
    case "$uv_path" in
        "$VIRTUAL_ENV"/*) return 0 ;;
        *) return 1 ;;
    esac
}

update_existing_uv() {
    if uv_self_update_supported; then
        run uv self update
        return 0
    fi

    if uv_installed_by_homebrew; then
        run brew upgrade uv
        return 0
    fi

    if uv_installed_by_pipx; then
        run pipx upgrade uv
        return 0
    fi

    if uv_installed_in_active_virtualenv; then
        run python -m pip install --upgrade uv
        return 0
    fi

    if uv_version_satisfies_minimum; then
        printf 'uv is already installed and satisfies >=%s; skipping automatic uv update because the install source was not detected.\n' "$MIN_UV_VERSION"
        return 0
    fi

    version=$(current_uv_version 2>/dev/null || printf 'unknown')
    fail "uv $MIN_UV_VERSION or newer is required; found uv $version. The existing uv install source was not detected. Upgrade uv manually with the package manager that installed it, then rerun this installer."
}

install_claude_if_missing() {
    if command -v claude >/dev/null 2>&1; then
        printf 'Claude Code already found on PATH; skipping install.\n'
        return 0
    fi

    require_command npm
    # On macOS with Homebrew node, npm install -g may fail without
    # --prefix. Auto-detect the global prefix to avoid permission errors.
    if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        run npm install -g --prefix "$(brew --prefix)" @anthropic-ai/claude-code
    else
        run npm install -g @anthropic-ai/claude-code
    fi
}

install_codex_if_missing() {
    if command -v codex >/dev/null 2>&1; then
        printf 'Codex already found on PATH; skipping install.\n'
        return 0
    fi

    require_command npm
    # On macOS with Homebrew node, npm install -g may fail without
    # --prefix. Auto-detect the global prefix to avoid permission errors.
    if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        run npm install -g --prefix "$(brew --prefix)" @openai/codex
    else
        run npm install -g @openai/codex
    fi
}

install_or_update_uv() {
    add_uv_to_path

    if command -v uv >/dev/null 2>&1; then
        update_existing_uv
        validate_uv_version
        return 0
    fi

    run_uv_installer
    add_uv_to_path

    if [ "$dry_run" -eq 0 ] && ! command -v uv >/dev/null 2>&1; then
        fail "uv was installed, but it is not available on PATH. Open a new terminal or add uv's bin directory to PATH."
    fi

    validate_uv_version
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --voice-nim)
                voice_nim=1
                ;;
            --voice-local)
                voice_local=1
                ;;
            --voice-all)
                voice_all=1
                ;;
            --torch-backend)
                shift
                [ "$#" -gt 0 ] || fail "--torch-backend requires a value."
                torch_backend="$1"
                [ -n "$torch_backend" ] || fail "--torch-backend requires a non-empty value."
                ;;
            --torch-backend=*)
                torch_backend="${1#*=}"
                [ -n "$torch_backend" ] || fail "--torch-backend requires a non-empty value."
                ;;
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

validate_args() {
    include_local=$voice_local

    if [ "$voice_all" -eq 1 ]; then
        include_local=1
    fi

    if [ -n "$torch_backend" ] && [ "$include_local" -ne 1 ]; then
        fail "--torch-backend requires --voice-local or --voice-all."
    fi
}

# Clone or update the Claude Unbound repository.
# In dev mode (running from inside the repo), creates a symlink so
# wrappers have a stable path. In standard mode, clones or updates.
clone_or_update_repo() {
    local actual_repo_dir
    actual_repo_dir=$(resolve_repo_dir)

    if [ "$actual_repo_dir" != "$REPO_DIR" ]; then
        # Developer mode: script is running from inside the repo.
        # Create a symlink so the wrappers have a stable path.
        if [ -e "$REPO_DIR" ] && ! is_symlink_to "$REPO_DIR" "$actual_repo_dir"; then
            fail "$REPO_DIR exists and is not a symlink to $actual_repo_dir. Remove it or set FCC_REPO_DIR."
        fi
        if [ ! -e "$REPO_DIR" ]; then
            run ln -s "$actual_repo_dir" "$REPO_DIR"
        fi
        # Record dev mode for uninstall.sh
        mkdir -p "$HOME/$FCC_HOME_DIRNAME"
        printf 'dev\n' > "$HOME/$FCC_HOME_DIRNAME/.install_mode"
        return 0
    fi

    # Standard mode: clone or update
    mkdir -p "$HOME/$FCC_HOME_DIRNAME"
    printf 'clone\n' > "$HOME/$FCC_HOME_DIRNAME/.install_mode"

    if [ -d "$REPO_DIR/.git" ]; then
        printf 'Repository already exists at %s; updating...\n' "$REPO_DIR"
        if [ "$dry_run" -eq 0 ]; then
            (cd "$REPO_DIR" && git pull --ff-only 2>/dev/null) || {
                printf 'WARNING: git pull failed (local modifications?). Continuing with existing checkout.\n'
            }
        fi
    else
        if [ -e "$REPO_DIR" ]; then
            fail "$REPO_DIR exists but is not a git repository. Remove it manually and rerun."
        fi
        run git clone "$REPO_HTTPS_URL" "$REPO_DIR"
    fi
}

# Create wrapper scripts in ~/.local/bin/ that invoke uv run from the
# live source tree. This ensures source changes are picked up immediately.
create_wrappers() {
    local bin_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
    mkdir -p "$bin_dir"

    for cmd in fcc-server fcc-claude fcc-codex fcc-init free-claude-code; do
        local wrapper="$bin_dir/$cmd"
        # Remove old symlink (from previous uv tool install)
        [ -L "$wrapper" ] && rm -f "$wrapper"

        cat > "$wrapper" <<WRAPPER
#!/usr/bin/env bash
# Auto-generated by install.sh — edits will be overwritten on next install.
exec uv run --project "$REPO_DIR" $cmd "\$@"
WRAPPER
        chmod +x "$wrapper"

        printf 'Created wrapper: %s\n' "$wrapper"
    done
}

# Install voice extras into the project venv via uv sync.
sync_repo_extras() {
    local extras=""

    if [ "$voice_all" -eq 1 ]; then
        extras="voice voice_local"
    elif [ "$voice_nim" -eq 1 ] && [ "$voice_local" -eq 1 ]; then
        extras="voice voice_local"
    elif [ "$voice_nim" -eq 1 ]; then
        extras="voice"
    elif [ "$voice_local" -eq 1 ]; then
        extras="voice_local"
    fi

    local sync_args="uv sync --directory $REPO_DIR"
    for extra in $extras; do
        sync_args="$sync_args --extra $extra"
    done
    if [ -n "$torch_backend" ]; then
        sync_args="$sync_args --torch-backend $torch_backend"
    fi

    run sh -c "$sync_args"
}

# Configure MCP Router state: create config from template, create state
# directories, and bootstrap the MCP Router venv.
setup_mcp_router() {
    local mcp_config_file="$HOME/$FCC_HOME_DIRNAME/mcp_config.json"
    local mcp_config_example="$REPO_DIR/scripts/mcp/mcp_config.example.json"

    # Create mcp_config.json from template if missing
    if [ ! -f "$mcp_config_file" ] && [ -f "$mcp_config_example" ]; then
        mkdir -p "$HOME/$FCC_HOME_DIRNAME"
        cp "$mcp_config_example" "$mcp_config_file"
        chmod 600 "$mcp_config_file"
        printf 'Created %s from example template.\n' "$mcp_config_file"
        printf '  Edit this file with real secrets before using MCP backends.\n'
    fi

    # Create MCP Router state directories
    mkdir -p "$HOME/.mcp-router/run" "$HOME/.mcp-router/logs" "$HOME/.mcp-router/sockets"

    # Bootstrap MCP Router venv (triggers dependency resolution)
    if [ -f "$REPO_DIR/scripts/mcp/pyproject.toml" ]; then
        run uv sync --directory "$REPO_DIR/scripts/mcp" --quiet 2>/dev/null || true
    fi
}

# Print guidance about MCP Router dependencies (non-fatal).
print_mcp_dependency_guidance() {
    mcp_missing=""
    for cmd in npx socat jq; do
        command -v "$cmd" >/dev/null 2>&1 || mcp_missing="$mcp_missing $cmd"
    done
    if [ -n "$mcp_missing" ]; then
        printf '\nMCP Router: the following dependencies are missing:%s\n' "$mcp_missing"
        printf '  The MCP Router requires them to start.\n'
        printf '  Install commands:\n'
        printf '    Debian/Ubuntu:  sudo apt-get install -y socat jq nodejs npm\n'
        printf '    macOS (brew):   brew install socat jq node\n'
        printf '    Arch Linux:     sudo pacman -S socat jq nodejs npm\n'
        printf '  After installing, start the MCP Router with: bash scripts/mcp/start_mcp.sh\n'
    fi
}

parse_args "$@"
validate_args

# Resolve the Claude Unbound repository URL AFTER argv parsing so
# --help / --dry-run short-circuits above don't pay this cost.
REPO_HTTPS_URL=$(resolve_repo_https_url) || exit 1

step "Installing Claude Code if missing"
install_claude_if_missing

step "Installing Codex if missing"
install_codex_if_missing

step "Installing uv if missing, updating if present"
install_or_update_uv

step "Installing Python $PYTHON_VERSION"
run uv python install "$PYTHON_VERSION"

step "Cloning or updating Claude Unbound repository"
clone_or_update_repo

step "Creating wrapper scripts"
create_wrappers

step "Syncing project dependencies"
sync_repo_extras

step "Setting up MCP Router"
setup_mcp_router

# Install the spawn-claude-tab skill to ~/.claude/skills/ so Claude Code
# agents in any repo can spawn new orange kitty tabs.
install_skill() {
    local src="$REPO_DIR/skills/spawn-claude-tab"
    local dest="$HOME/.claude/skills/spawn-claude-tab"

    if [ ! -d "$src" ]; then
        printf 'WARNING: skill source not found at %s; skipping skill install.\n' "$src"
        return 0
    fi

    mkdir -p "$dest"
    run cp "$src/SKILL.md" "$dest/SKILL.md"
    printf 'Installed skill: %s/SKILL.md\n' "$dest"
}

step "Installing Claude Code skill"
install_skill

printf '\nClaude Unbound is installed. We recommend using the launcher.sh script within the scripts folder for launching everything simultaneously via a kitty terminal window.\n'
printf 'Alternatively, you can run everything seperately (except the MCP Router) with the following commands:\n'
printf 'Start the proxy with: fcc-server\n'
printf 'Run Claude Code with: fcc-claude\n'
printf 'Run Codex with: fcc-codex\n'

print_mcp_dependency_guidance
