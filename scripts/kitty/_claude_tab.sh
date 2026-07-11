#!/bin/bash
# Runs *inside* a freshly-spawned Claude Code tab.
#
# Best-effort: colours this tab orange via `kitten @ set-tab-color --self`
# (kitty exports KITTY_LISTEN_ON into child processes when launched with
# --listen-on, so no --to is needed). A missing `kitten` never blocks the
# session — the colour step is simply skipped.
#
# Then `exec`s into `uv run fcc-claude`, which self-injects the proxy env
# via the existing ClaudeCliAdapter / launch_claude logic in
# cli/entrypoints.py + cli/adapters/claude.py. No env logic is copied here.

# Claude Code palette (orange).
CLAUDE_ACTIVE_BG="#e08a2b"
CLAUDE_ACTIVE_FG="#1a1205"
CLAUDE_INACTIVE_BG="#3a2410"
CLAUDE_INACTIVE_FG="#e0a85f"

if command -v kitten >/dev/null 2>&1; then
    kitten @ set-tab-color --self \
        "active_bg=$CLAUDE_ACTIVE_BG" \
        "active_fg=$CLAUDE_ACTIVE_FG" \
        "inactive_bg=$CLAUDE_INACTIVE_BG" \
        "inactive_fg=$CLAUDE_INACTIVE_FG" \
        >/dev/null 2>&1 || true
fi

# Resolve repo root (this script lives at <repo>/scripts/kitty/_claude_tab.sh)
# so `uv run` resolves the project.
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR" || true

exec uv run fcc-claude "$@"
