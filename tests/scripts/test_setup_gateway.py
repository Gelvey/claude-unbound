"""Tests for scripts/claude-desktop/setup-gateway.sh."""

import json
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script_text() -> str:
    return (_repo_root() / "scripts" / "claude-desktop" / "setup-gateway.sh").read_text(
        encoding="utf-8"
    )


def _extract_func(text: str, declaration: str) -> str:
    """Extract a shell function (declaration through matching closing brace)."""
    start = text.index(declaration)
    brace_start = text.index("{", start)
    depth = 0
    for index, char in enumerate(text[brace_start:], start=brace_start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"Unclosed function body for {declaration}")


def _helpers_text() -> str:
    """Extract the dotenv + curation helpers so they can be sourced in isolation."""
    text = _script_text()
    return (
        _extract_func(text, "_env_val() {")
        + "\n"
        + _extract_func(text, "_curated_models_json() {")
        + "\n"
        + _extract_func(text, "_managed_mcp_servers_json() {")
    )


def _extract_sandbox_json(text: str) -> str:
    """Pull the SANDBOX_JSON single-quoted literal out of the script."""
    marker = "SANDBOX_JSON='"
    start = text.index(marker) + len(marker)
    # The literal is single-quoted, so it ends at the next unescaped "'".
    end = text.index("'", start)
    return text[start:end]


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------
def test_setup_gateway_sh_is_valid_bash() -> None:
    """setup-gateway.sh passes bash -n syntax check."""
    script = _repo_root() / "scripts" / "claude-desktop" / "setup-gateway.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Multi-platform managed-settings path resolution
# ---------------------------------------------------------------------------
def test_setup_gateway_supports_macos_path() -> None:
    """setup-gateway.sh resolves macOS managed settings path."""
    text = _script_text()
    body = _extract_func(text, "resolve_managed_dir() {")
    assert "Darwin" in body
    assert "/Library/Application Support/Claude" in body


def test_setup_gateway_supports_linux_official_path() -> None:
    """setup-gateway.sh resolves Linux official beta managed settings path."""
    text = _script_text()
    body = _extract_func(text, "resolve_managed_dir() {")
    # The official Linux path is /etc/claude (not /etc/claude-desktop).
    # In the shell script, \n is a literal two-char sequence, so we check
    # for the printf argument that outputs the official path.
    assert "printf '/etc/claude\\n'" in body or "printf '/etc/claude'" in body


def test_setup_gateway_supports_linux_unofficial_path() -> None:
    """setup-gateway.sh keeps backward compat with unofficial build path."""
    text = _script_text()
    body = _extract_func(text, "resolve_managed_dir() {")
    assert "claude-desktop-unofficial" in body
    assert "/etc/claude-desktop" in body


def test_setup_gateway_has_variant_override() -> None:
    """setup-gateway.sh supports CLAUDE_DESKTOP_VARIANT override."""
    text = _script_text()
    body = _extract_func(text, "resolve_managed_dir() {")
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


# ---------------------------------------------------------------------------
# Sandbox configuration (filesystem isolated, network open, git/gh excluded)
# ---------------------------------------------------------------------------
def test_setup_gateway_keeps_filesystem_isolation() -> None:
    """setup-gateway.sh keeps filesystem isolation on (sandbox enabled)."""
    text = _script_text()
    sandbox = json.loads(_extract_sandbox_json(text))
    assert sandbox["enabled"] is True
    # Filesystem layer stays on — no `filesystem.disabled` escape.
    assert sandbox.get("filesystem", {}).get("disabled") is not True


def test_setup_gateway_allows_all_network() -> None:
    """setup-gateway.sh opens network egress to any host while sandboxed."""
    text = _script_text()
    sandbox = json.loads(_extract_sandbox_json(text))
    # Catch-all so networked commands stay sandboxed (filesystem stays
    # restricted) instead of falling back to unsandboxed execution.
    assert sandbox["network"]["allowedDomains"] == ["*"]


def test_setup_gateway_allows_toolchain_caches_write() -> None:
    """setup-gateway.sh permits writes to uv/npm/pnpm/playwright caches."""
    text = _script_text()
    sandbox = json.loads(_extract_sandbox_json(text))
    allow = sandbox["filesystem"]["allowWrite"]
    # Python (uv/pip) and Node (npm/pnpm/yarn) + browser e2e caches must be
    # writable so dep install and test runs work under filesystem isolation.
    for path in (
        "~/.cache/uv",
        "~/.local/share/uv",
        "~/.cache/pip",
        "~/.npm",
        "~/.local/share/pnpm",
        "~/.pnpm-store",
        "~/.cache/ms-playwright",
    ):
        assert path in allow, f"missing allowWrite entry: {path}"


def test_setup_gateway_excludes_git_and_gh() -> None:
    """git/gh run outside the sandbox so credential helpers/keyring work."""
    text = _script_text()
    sandbox = json.loads(_extract_sandbox_json(text))
    excluded = sandbox["excludedCommands"]
    # `git *` matches `git push origin main`; bare `git` covers no-args.
    assert "git" in excluded
    assert "git *" in excluded
    assert "gh" in excluded
    assert "gh *" in excluded


def test_setup_gateway_emits_sandbox_into_managed_json() -> None:
    """The base jq invocation threads the sandbox block into the output object."""
    text = _script_text()
    # The base SETTINGS_JSON is built once with jq -n (sandbox included),
    # then inferenceModels / managedMcpServers are layered on via jq pipes.
    assert text.count('--argjson sandbox "$SANDBOX_JSON"') >= 1
    assert text.count("sandbox: $sandbox") >= 1


# ---------------------------------------------------------------------------
# Curated model list (_curated_models_json)
# ---------------------------------------------------------------------------
def test_curated_models_json_builds_gateway_ids(tmp_path: Path) -> None:
    """_curated_models_json emits Anthropic-family routes, MODEL first, deduped by ref.

    The desktop's inferenceModels validator requires "claude-*" or
    "anthropic/claude-*" routes; raw provider refs are rejected. Each
    configured tier maps to an Anthropic-family route that the gateway routes
    by tier substring (opus/sonnet/haiku -> tier model, else -> MODEL). A
    duplicate underlying ref (MODEL == MODEL_HAIKU here) is deduped so the
    picker shows a route once.
    """
    # Fake .env with a duplicate ref (MODEL == MODEL_HAIKU) to exercise dedup,
    # and a quoted value to exercise quote-stripping.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL=open_router/deepseek/deepseek-v4-flash\n"
        'MODEL_OPUS="cloudflare_ai/@cf/zai-org/glm-5.2"\n'
        "MODEL_SONNET=\n"
        "MODEL_HAIKU=open_router/deepseek/deepseek-v4-flash\n"
        "PORT=9999\n",
        encoding="utf-8",
    )
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _helpers_text() + f'\nFCC_ENV="{env_file}"\necho "$(_curated_models_json)"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"_curated_models_json failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    ids = json.loads(result.stdout.strip())
    # MODEL (default) first; MODEL_OPUS second; MODEL_SONNET empty -> skipped;
    # MODEL_HAIKU shares MODEL's ref -> deduped out. labelOverride hides the
    # date stamp; name (routing) is the full id.
    assert ids == [
        {"name": "anthropic/claude-default", "labelOverride": "Claude Default"},
        {"name": "anthropic/claude-opus-4-20250514", "labelOverride": "Claude Opus 4"},
    ]


def test_curated_models_json_all_tiers(tmp_path: Path) -> None:
    """With all four tiers set to distinct refs, all four routes appear."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL=open_router/deepseek/deepseek-v4-flash\n"
        "MODEL_OPUS=cloudflare_ai/@cf/zai-org/glm-5.2\n"
        "MODEL_SONNET=freebuff/mimo/mimo-v2.5-pro\n"
        "MODEL_HAIKU=open_router/z-ai/glm-5.2\n"
        "PORT=9999\n",
        encoding="utf-8",
    )
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _helpers_text() + f'\nFCC_ENV="{env_file}"\necho "$(_curated_models_json)"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    ids = json.loads(result.stdout.strip())
    assert ids == [
        {"name": "anthropic/claude-default", "labelOverride": "Claude Default"},
        {"name": "anthropic/claude-opus-4-20250514", "labelOverride": "Claude Opus 4"},
        {
            "name": "anthropic/claude-sonnet-4-20250514",
            "labelOverride": "Claude Sonnet 4",
        },
        {
            "name": "anthropic/claude-haiku-4-20250514",
            "labelOverride": "Claude Haiku 4",
        },
    ]


def test_curated_models_json_empty_without_model(tmp_path: Path) -> None:
    """No MODEL var -> empty output (caller omits inferenceModels)."""
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_OPUS=cloudflare_ai/x/y\nPORT=9999\n", encoding="utf-8")
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _helpers_text()
        + f'\nFCC_ENV="{env_file}"\nr=$(_curated_models_json); echo "result=[${{r}}]"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "result=[]"


def test_no_proxy_fetch_fallback_for_inference_models() -> None:
    """The install path must not fall back to fetching the proxy catalog for
    inferenceModels.

    The desktop's managed-settings validator requires every inferenceModels
    entry to be an Anthropic-family route ("claude-*" or "anthropic/claude-*").
    The proxy catalog returns raw provider refs (e.g.
    "anthropic/open_router/deepseek/deepseek-v4-flash") that the validator
    rejects, leaving the desktop in an invalid_config state. So when no MODEL
    env var is set the script must omit inferenceModels entirely rather than
    emit raw refs from a proxy fetch. This test is a regression guard against
    re-adding the fetch fallback: it checks the do_install function body (the
    code that builds MODELS_JSON) and the MODELS_SOURCE assignments in it.
    """
    text = _script_text()
    install_body = _extract_func(text, "do_write() {")
    # No curl fetch of the proxy model catalog in the install path.
    assert "curl -sf" not in install_body, (
        "do_install must not curl the proxy catalog: raw provider refs are "
        "rejected by the desktop validator"
    )
    assert 'MODELS_SOURCE="fetched"' not in install_body, (
        "do_install must not set MODELS_SOURCE=fetched: the proxy-fetch "
        "fallback was removed to prevent invalid configs"
    )


# ---------------------------------------------------------------------------
# Ownership grant (launcher refreshes managed settings without root)
# ---------------------------------------------------------------------------
def test_can_write_managed_helper_exists() -> None:
    """_can_write_managed and _grant_ownership helpers are present so the
    launcher can refresh managed settings unprivileged after a one-time
    `sudo setup-gateway.sh` ownership grant.
    """
    text = _script_text()
    assert "_can_write_managed() {" in text, (
        "setup-gateway.sh must define _can_write_managed so do_write can "
        "skip elevation when the managed dir is already user-writable"
    )
    assert "_grant_ownership() {" in text, (
        "setup-gateway.sh must define _grant_ownership so a sudo run "
        "transfers ownership of the managed dir to the invoking user"
    )


def test_do_write_uses_privilege_detection() -> None:
    """do_write only elevates when _can_write_managed fails, and grants
    ownership to SUDO_USER when elevated — so the first `sudo` run enables
    all later unprivileged launcher refreshes.
    """
    text = _script_text()
    body = _extract_func(text, "do_write() {")
    assert "_can_write_managed" in body, (
        "do_write must call _can_write_managed to detect an already-granted dir"
    )
    # The grant is invoked from do_write so an elevated run hands ownership
    # to the invoking user.
    assert "_grant_ownership" in body
    # When not elevated, the file is installed WITHOUT -o root -g root (those
    # require root and would defeat the unprivileged refresh path).
    assert 'install -m 0644 "$_tmpfile" "$MANAGED_FILE"' in body, (
        "do_write must install the file unprivileged (no -o root) when "
        "_can_write_managed succeeds, so the launcher can refresh it"
    )


def test_do_unwire_uses_privilege_detection() -> None:
    """do_unwire only elevates when the managed dir is not writable by us,
    so unwiring works unprivileged after the ownership grant.
    """
    text = _script_text()
    body = _extract_func(text, "do_unwire() {")
    assert '"$MANAGED_DIR"' in body and "priv_prefix" in body
    # It checks dir writability before elevating (removing needs write on the
    # dir, not the file).
    assert '[ ! -w "$MANAGED_DIR" ]' in body, (
        "do_unwire must check the managed dir is writable before elevating"
    )


def test_can_write_managed_file_writable(tmp_path: Path) -> None:
    """_can_write_managed returns 0 (success) when the managed file exists
    and is writable by us — the post-grant state the launcher relies on.
    """
    managed_dir = tmp_path / "claude-desktop"
    managed_dir.mkdir()
    managed_file = managed_dir / "managed-settings.json"
    managed_file.write_text("{}", encoding="utf-8")
    managed_file.chmod(0o644)
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _extract_func(_script_text(), "_can_write_managed() {")
        + f'\nMANAGED_DIR="{managed_dir}"\nMANAGED_FILE="{managed_file}"\n'
        "_can_write_managed && echo WRITABLE || echo NOT_WRITABLE\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "WRITABLE", (
        f"_can_write_managed should succeed for a user-writable file; "
        f"got: {result.stdout!r} stderr={result.stderr!r}"
    )


def test_can_write_managed_root_owned_file_not_writable(tmp_path: Path) -> None:
    """_can_write_managed returns non-zero when the file exists but is not
    writable by us (e.g. root-owned 0644) — the pre-grant state that should
    trigger elevation.
    """
    managed_dir = tmp_path / "claude-desktop"
    managed_dir.mkdir()
    managed_file = managed_dir / "managed-settings.json"
    managed_file.write_text("{}", encoding="utf-8")
    # 0444 = read-only for everyone; not writable by the unprivileged user.
    managed_file.chmod(0o444)
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _extract_func(_script_text(), "_can_write_managed() {")
        + f'\nMANAGED_DIR="{managed_dir}"\nMANAGED_FILE="{managed_file}"\n'
        # Run as the current (non-root) user; if we ARE root in CI, skip the
        # writability assertion since root bypasses file perms.
        'if [ "$(id -u)" -eq 0 ]; then echo SKIP_ROOT; '
        "else _can_write_managed && echo WRITABLE || echo NOT_WRITABLE; fi\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout.strip()
    if out == "SKIP_ROOT":
        return  # running as root in CI — root bypasses perms, nothing to assert
    assert out == "NOT_WRITABLE", (
        f"_can_write_managed should fail for a read-only file; got {out!r}"
    )


# ---------------------------------------------------------------------------
# MCP server mirroring (_managed_mcp_servers_json)
# ---------------------------------------------------------------------------
def test_managed_mcp_servers_mirrors_claude_json(tmp_path: Path) -> None:
    """_managed_mcp_servers_json converts ~/.claude.json mcpServers (object
    keyed by name with "type") into the desktop's managedMcpServers array
    (objects with "name" + "transport"), dropping unsupported transports."""
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "mcp-router": {
                        "type": "stdio",
                        "command": "/usr/local/bin/mcp-proxy-tool",
                        "args": ["-p", "/tmp/router.sock"],
                        "_comment": "should be dropped",
                    },
                    "graphify": {"type": "http", "url": "http://127.0.0.1:7120/mcp"},
                    "websocket-only": {"type": "ws", "url": "ws://example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _helpers_text()
        + f'\n_mcp=$(_managed_mcp_servers_json "{claude_json}")\necho "$_mcp"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"_managed_mcp_servers_json failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    servers = json.loads(result.stdout.strip())
    # ws transport is unsupported by managedMcpServers -> dropped; _comment dropped.
    assert servers == [
        {
            "name": "mcp-router",
            "transport": "stdio",
            "command": "/usr/local/bin/mcp-proxy-tool",
            "args": ["-p", "/tmp/router.sock"],
        },
        {"name": "graphify", "transport": "http", "url": "http://127.0.0.1:7120/mcp"},
    ]


def test_managed_mcp_servers_empty_without_file(tmp_path: Path) -> None:
    """No ~/.claude.json -> empty output (no managedMcpServers written)."""
    wrapper = tmp_path / "run.sh"
    wrapper.write_text(
        _helpers_text()
        + f'\nr=$(_managed_mcp_servers_json "{tmp_path / "missing.json"}"); '
        'echo "result=[${r}]"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(wrapper)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "result=[]"
