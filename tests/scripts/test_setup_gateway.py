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
    """_curated_models_json emits deduped anthropic/{ref} IDs, MODEL first."""
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
    assert ids == [
        "anthropic/open_router/deepseek/deepseek-v4-flash",
        "anthropic/cloudflare_ai/@cf/zai-org/glm-5.2",
    ]


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
