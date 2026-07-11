---
name: spawn-claude-tab
description: Open a new orange Claude Code tab in the Claude Unbound kitty window — for parallelising plan phases or running side sessions.
---

# Spawn Claude Code Tab

Opens a new **orange** Claude Code tab in the Claude Unbound kitty window.

## Usage

Run this from inside any Claude Code session that lives in the Claude Unbound kitty window:

```bash
bash "$HOME/claude-unbound/scripts/kitty/new_claude_tab.sh"
```

Pass an optional label to name the tab (e.g. the phase or task):

```bash
bash "$HOME/claude-unbound/scripts/kitty/new_claude_tab.sh" "Phase 2"
```

The new tab will appear as:

- **No label:** `Claude Code`
- **With label:** `Claude Code — Phase 2`

Each new tab is an independent, interactive Claude Code session that auto-connects to the Claude Unbound proxy (the same `uv run fcc-claude` entry point as the main CLI tab). No extra wiring is needed — `fcc-claude` self-configures its proxy env from `~/.fcc/.env`.

The tab colours itself orange via `kitten @ set-tab-color --self`, matching the other Claude Code tabs.

## Overriding the repo path

If the repo is not at `~/claude-unbound`, set `$CLAUDE_UNBOUND_DIR` before running:

```bash
CLAUDE_UNBOUND_DIR="$HOME/path/to/claude-unbound" \
  bash "$CLAUDE_UNBOUND_DIR/scripts/kitty/new_claude_tab.sh" "My Phase"
```

## Limitations

- **Only works inside the Claude Unbound kitty window.** It requires `kitten` on PATH and `$KITTY_LISTEN_ON` to be set (automatic when the window was launched with `--listen-on`).
- If invoked outside the kitty window (e.g. from an SSH session or a different terminal), the script exits non-zero with a clear message: `"This only works inside the Claude Unbound kitty window."` Do not retry — the user needs to be in the kitty window.
- Each new tab is a standalone interactive session. Use the label to communicate what phase or task it runs, then drive it manually or from within that tab.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Exit 1: "kitten not found" | `kitten` is not on PATH | Make sure kitty is installed and its `bin` is in PATH |
| Exit 1: "$KITTY_LISTEN_ON is not set" | Running outside the kitty window | Run this from a tab inside the Claude Unbound kitty window |
| Tab opens but is uncoloured | `kitten @` succeeded but the tab colour call failed | The session still works — the colour is cosmetic only |
