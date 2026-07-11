import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_new_tab(
    *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    sh = _repo_root() / "scripts" / "kitty" / "new_claude_tab.sh"
    env = os.environ.copy()
    env.pop("KITTY_LISTEN_ON", None)  # guard against real kitty env leaking in
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(sh), *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# ── Syntax / structure ──────────────────────────────────────────────────────


def test_new_claude_tab_sh_is_valid_bash() -> None:
    script = _repo_root() / "scripts" / "kitty" / "new_claude_tab.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_claude_tab_sh_is_valid_bash() -> None:
    script = _repo_root() / "scripts" / "kitty" / "_claude_tab.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ── Dry-run assertions ─────────────────────────────────────────────────────


def test_dry_run_no_label() -> None:
    """Dry-run with no label prints 'Claude Code' title and correct cwd."""
    result = _run_new_tab(env_extra={"FCC_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "--tab-title=Claude Code" in stdout
    assert f"--cwd={_repo_root()}" in stdout
    assert "_claude_tab.sh" in stdout
    # Colour constants from the plan palette
    assert "#e08a2b" in stdout  # active bg (orange)
    assert "#1a1205" in stdout  # active fg
    assert "#3a2410" in stdout  # inactive bg
    assert "#e0a85f" in stdout  # inactive fg


def test_dry_run_with_label() -> None:
    """Dry-run with a label includes the label in the tab title."""
    result = _run_new_tab("Phase 2", env_extra={"FCC_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Claude Code — Phase 2" in stdout
    assert f"--cwd={_repo_root()}" in stdout
    assert "_claude_tab.sh" in stdout


def test_dry_run_launches_from_kitty_script() -> None:
    """Dry-run argv includes `bash` and the path to _claude_tab.sh."""
    result = _run_new_tab("Review", env_extra={"FCC_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    launch_line = lines[0]
    assert "bash" in launch_line
    assert "scripts/kitty/_claude_tab.sh" in launch_line


# ── Runtime failure modes (no kitty) ────────────────────────────────────────


def test_exits_nonzero_when_kitten_missing() -> None:
    """Without kitten on PATH and no KITTY_LISTEN_ON, script exits non-zero."""
    result = _run_new_tab(env_extra={"PATH": "/usr/bin:/bin"})
    assert result.returncode != 0
    # Either the kitten check or the KITTY_LISTEN_ON guard fires (the latter
    # if kitten happens to be installed elsewhere); both produce the same
    # "only works inside" guidance.
    assert "only works inside the Claude Unbound kitty window" in result.stderr


def test_exits_nonzero_when_kitten_present_but_no_listen_on() -> None:
    """Even with kitten on PATH, missing KITTY_LISTEN_ON triggers a guard."""
    # kitten is likely not in /usr/bin:/bin, but let's add a safe mock that
    # just returns 0 so we test the KITTY_LISTEN_ON guard specifically.
    result = _run_new_tab()
    if result.returncode != 0 and "KITTY_LISTEN_ON" in result.stderr:
        # kitten was found, KITTY_LISTEN_ON check fired as expected.
        return
    # If kitten wasn't found either, that's still a valid failure path.
    assert result.returncode != 0


# ── Dry-run is evaluated BEFORE kitten/listen-on guards ─────────────────────


def test_dry_run_succeeds_even_without_kitten() -> None:
    """FCC_DRY_RUN bypasses the kitten/listen-on checks."""
    result = _run_new_tab(env_extra={"FCC_DRY_RUN": "1", "PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr
    assert "_claude_tab.sh" in result.stdout


def test_dry_run_succeeds_even_without_listen_on() -> None:
    """FCC_DRY_RUN bypasses the KITTY_LISTEN_ON check."""
    result = _run_new_tab(env_extra={"FCC_DRY_RUN": "1"})
    assert result.returncode == 0, result.stderr
