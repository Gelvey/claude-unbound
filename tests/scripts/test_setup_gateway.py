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


def test_curated_models_json_empty_without_model(tmp_path: Path) -> None:
    """No MODEL var -> empty output (caller falls back to proxy fetch)."""
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
