#!/bin/bash
# Spawn a new orange Claude Code tab in the Claude Unbound kitty window.
#
# Usage: new_claude_tab.sh [label]
#   label  Optional label appended to the tab title, e.g. "Phase 2"
#          → tab title "Claude Code — Phase 2".
#
# Env:
#   FCC_DRY_RUN=1   Echo the resolved `kitten @ launch` argv instead of
#                   launching. Lets the skill / users preview, and the test
#                   suite exercise this script without a display or kitty.
#
# The new tab colours itself via _claude_tab.sh (`--self`), so there is no
# fragile title-match race after launch. This script only works inside the
# Claude Unbound kitty window — it needs `kitten` and $KITTY_LISTEN_ON.

set -eu

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Claude Code palette (orange) — mirrored in _claude_tab.sh. Kept here so
# the dry-run preview can surface the colours that will be applied.
CLAUDE_ACTIVE_BG="#e08a2b"
CLAUDE_ACTIVE_FG="#1a1205"
CLAUDE_INACTIVE_BG="#3a2410"
CLAUDE_INACTIVE_FG="#e0a85f"

LABEL="${1:-}"
if [ -n "$LABEL" ]; then
    TITLE="Claude Code — $LABEL"
else
    TITLE="Claude Code"
fi

CLAUDE_TAB_SCRIPT="$REPO_DIR/scripts/kitty/_claude_tab.sh"

# Dry-run BEFORE the kitten/listen-on checks so it works in headless CI.
if [ -n "${FCC_DRY_RUN:-}" ]; then
    printf 'kitten @ launch --type=tab --tab-title=%s --cwd=%s bash %s\n' \
        "$TITLE" "$REPO_DIR" "$CLAUDE_TAB_SCRIPT"
    printf '# active_bg=%s active_fg=%s inactive_bg=%s inactive_fg=%s\n' \
        "$CLAUDE_ACTIVE_BG" "$CLAUDE_ACTIVE_FG" \
        "$CLAUDE_INACTIVE_BG" "$CLAUDE_INACTIVE_FG"
    exit 0
fi

if ! command -v kitten >/dev/null 2>&1; then
    echo "[fcc] new_claude_tab.sh: 'kitten' was not found on PATH." >&2
    echo "[fcc] This only works inside the Claude Unbound kitty window." >&2
    exit 1
fi

if [ -z "${KITTY_LISTEN_ON:-}" ]; then
    echo "[fcc] new_claude_tab.sh: \$KITTY_LISTEN_ON is not set." >&2
    echo "[fcc] This only works inside the Claude Unbound kitty window" >&2
    echo "[fcc] (a kitty launched with --listen-on)." >&2
    exit 1
fi

kitten @ launch \
    --type=tab \
    --tab-title="$TITLE" \
    --cwd="$REPO_DIR" \
    bash "$CLAUDE_TAB_SCRIPT"
