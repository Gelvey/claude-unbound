"""Tests for scripts/claude-desktop/setup-gateway.sh."""

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script_text() -> str:
    return (_repo_root() / "scripts" / "claude-desktop" / "setup-gateway.sh").read_text(
        encoding="utf-8"
    )


def _braced_body(text: str, declaration: str) -> str:
    """Extract the braced body of a shell function."""
    start = text.index(declaration)
    brace_start = text.index("{", start)
    depth = 0
    for index, char in enumerate(text[brace_start:], start=brace_start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : index]
    raise AssertionError(f"Unclosed function body for {declaration}")


def test_setup_gateway_is_valid_bash() -> None:
    """setup-gateway.sh passes bash -n syntax check."""
    script = _repo_root() / "scripts" / "claude-desktop" / "setup-gateway.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_setup_gateway_supports_macos_path() -> None:
    """setup-gateway.sh resolves macOS managed settings path."""
    text = _script_text()
    body = _braced_body(text, "resolve_managed_dir()")
    assert "Darwin" in body
    assert "/Library/Application Support/Claude" in body


def test_setup_gateway_supports_linux_official_path() -> None:
    """setup-gateway.sh resolves Linux official beta managed settings path."""
    text = _script_text()
    body = _braced_body(text, "resolve_managed_dir()")
    # The official Linux path is /etc/claude (not /etc/claude-desktop).
    # In the shell script, \n is a literal two-char sequence, so we check
    # for the printf argument that outputs the official path.
    assert "printf '/etc/claude\\n'" in body or "printf '/etc/claude'" in body


def test_setup_gateway_supports_linux_unofficial_path() -> None:
    """setup-gateway.sh keeps backward compat with unofficial build path."""
    text = _script_text()
    body = _braced_body(text, "resolve_managed_dir()")
    assert "claude-desktop-unofficial" in body
    assert "/etc/claude-desktop" in body


def test_setup_gateway_has_variant_override() -> None:
    """setup-gateway.sh supports CLAUDE_DESKTOP_VARIANT override."""
    text = _script_text()
    body = _braced_body(text, "resolve_managed_dir()")
    assert "CLAUDE_DESKTOP_VARIANT" in body
    assert "unofficial" in body
    assert "official" in body
    assert "macos" in body


def test_setup_gateway_help_mentions_all_platforms() -> None:
    """setup-gateway.sh --help text mentions all three variants."""
    text = _script_text()
    assert "macOS" in text
    assert "official beta" in text
    assert "unofficial" in text
    assert "/Library/Application Support/Claude" in text
    assert "/etc/claude" in text
    assert "/etc/claude-desktop" in text


def _extract_sandbox_json(text: str) -> str:
    """Pull the SANDBOX_JSON single-quoted literal out of the script."""
    marker = "SANDBOX_JSON='"
    start = text.index(marker) + len(marker)
    # The literal is single-quoted, so it ends at the next unescaped "'".
    end = text.index("'", start)
    return text[start:end]


def test_setup_gateway_disables_sandbox() -> None:
    """setup-gateway.sh disables the sandbox for CLI-like unrestricted access."""
    text = _script_text()
    sandbox = __import__("json").loads(_extract_sandbox_json(text))
    # Managed settings override Desktop's default-on sandbox.  Disabling it
    # gives unrestricted filesystem + network egress (any website reachable),
    # matching the CLI experience the user wants from a gateway-managed setup.
    assert sandbox["enabled"] is False
    # No network allowlist or excludedCommands — nothing is sandboxed.
    assert "network" not in sandbox
    assert "excludedCommands" not in sandbox


def test_setup_gateway_emits_sandbox_into_managed_json() -> None:
    """Both jq invocations thread the sandbox block into the output object."""
    text = _script_text()
    # Two jq -n blocks build SETTINGS_JSON (with and without models); both
    # must pass --argjson sandbox and include `sandbox: $sandbox`.
    assert text.count('--argjson sandbox "$SANDBOX_JSON"') >= 2
    assert text.count("sandbox: $sandbox") >= 2
