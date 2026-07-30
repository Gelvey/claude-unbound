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


def _extract_perms_json(text: str) -> str:
    """Pull the PERMS_JSON single-quoted literal out of the script."""
    marker = "PERMS_JSON='"
    start = text.index(marker) + len(marker)
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
# Web-research permissions (WebFetch / WebSearch)
#
# Web research uses the WebFetch/WebSearch tools, which are gated by
# permission rules — NOT by the Bash sandbox's network.allowedDomains (that
# only covers Bash subprocess egress). So the managed settings must carry a
# permissions.allow list so the desktop can visit websites for research
# without prompting on every fetch.
# ---------------------------------------------------------------------------
def test_setup_gateway_allows_web_research() -> None:
    """PERMS_JSON allows WebFetch to any domain plus WebSearch."""
    text = _script_text()
    perms = json.loads(_extract_perms_json(text))
    allow = perms["allow"]
    # WebFetch(domain:*) matches every domain (== bare WebFetch), so the
    # desktop can fetch any URL for research. WebSearch allows web search.
    assert "WebFetch(domain:*)" in allow, (
        "permissions.allow must include WebFetch(domain:*) so the desktop "
        "can visit websites for research without per-domain prompts"
    )
    assert "WebSearch" in allow, (
        "permissions.allow must include WebSearch for web research"
    )


def test_setup_gateway_threads_perms_into_managed_json() -> None:
    """The base jq invocation threads the permissions block into the output."""
    text = _script_text()
    assert text.count('--argjson perms "$PERMS_JSON"') >= 1
    assert text.count("permissions: $perms") >= 1


def test_setup_gateway_check_detects_stale_permissions() -> None:
    """do_check verifies the permissions.allow block so a stale managed file
    missing it is detected and refreshed on the next setup-gateway.sh run."""
    text = _script_text()
    body = _extract_func(text, "do_check() {")
    # do_check compares the stored permissions.allow against PERMS_JSON's
    # .allow, so a stale file (pre-permissions) fails --check and gets
    # rewritten instead of being left in place.
    assert ".permissions.allow" in body, (
        "do_check must verify permissions.allow so a stale managed file "
        "missing the web-research permissions is detected and refreshed"
    )
    assert "$PERMS_JSON" in body, (
        "do_check must compare stored permissions against PERMS_JSON"
    )


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
        {"name": "anthropic/claude-default", "labelOverride": "Claude Unbound Default"},
        {
            "name": "anthropic/claude-opus-4-20250514",
            "labelOverride": "Claude Opus Unbound",
        },
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
        {"name": "anthropic/claude-default", "labelOverride": "Claude Unbound Default"},
        {
            "name": "anthropic/claude-opus-4-20250514",
            "labelOverride": "Claude Opus Unbound",
        },
        {
            "name": "anthropic/claude-sonnet-4-20250514",
            "labelOverride": "Claude Sonnet Unbound",
        },
        {
            "name": "anthropic/claude-haiku-4-20250514",
            "labelOverride": "Claude Haiku Unbound",
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
# Root ownership of the managed-settings file (trust requirement)
# ---------------------------------------------------------------------------
def test_managed_file_installed_root_owned() -> None:
    """do_write installs the managed file root-owned and never chowns it to a
    non-root user.

    The Claude Desktop trust check rejects a managed-settings.json that is
    not owned by root (logging "must be owned by root and not group- or
    world-writable") and falls back to the default claude.ai login. A prior
    change added an ownership grant that chowned the managed dir to the
    invoking user for "rootless refresh"; that broke the trust check, so the
    desktop prompted for an Anthropic login. This test is a regression guard:
    the install path must always install the file root-owned, and the
    ownership-grant helpers (_can_write_managed / _grant_ownership) must not
    exist.
    """
    text = _script_text()
    body = _extract_func(text, "do_write() {")
    # The file is installed root-owned, unconditionally.
    assert 'install -m 0644 -o root -g root "$_tmpfile" "$MANAGED_FILE"' in body, (
        "do_write must install managed-settings.json root-owned: the desktop "
        "trust check rejects a user-owned file and falls back to claude.ai login"
    )
    # The dir is created root-owned.
    assert 'install -d -m 0755 -o root -g root "$MANAGED_DIR"' in body, (
        "do_write must create the managed dir root-owned"
    )
    # The ownership-grant helpers that broke trust must not be present.
    assert "_can_write_managed" not in text, (
        "_can_write_managed must not exist: it enabled rootless refresh by "
        "detecting a user-owned dir, which the desktop rejects as untrusted"
    )
    assert "_grant_ownership" not in text, (
        "_grant_ownership must not exist: it chowned the managed dir to the "
        "invoking user, breaking the desktop's root-ownership trust check"
    )
    # No unprivileged install path (no `install -m 0644 "$_tmpfile"` without
    # -o root) that would produce a user-owned file.
    assert 'install -m 0644 "$_tmpfile"' not in body, (
        "do_write must not install the file unprivileged (no -o root): a "
        "user-owned managed file is rejected by the desktop trust check"
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
