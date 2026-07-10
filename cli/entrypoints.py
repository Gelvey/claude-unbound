"""CLI entry points for the installed package."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import uvicorn

from api.admin_urls import local_admin_url, local_proxy_root_url
from api.app import GracefulLifespanApp, create_app
from cli.adapters.base import ClientCliAdapter
from cli.adapters.claude import CLAUDE_CLI_ADAPTER
from cli.adapters.codex import CODEX_CLI_ADAPTER
from cli.codex_model_catalog import (
    build_codex_model_catalog,
    write_codex_model_catalog,
)
from cli.process_registry import (
    kill_all_best_effort,
    kill_pid_tree_best_effort,
    register_pid,
    unregister_pid,
)
from config.paths import (
    codex_model_catalog_path,
    config_dir_path,
    legacy_env_paths,
    managed_env_path,
)
from config.settings import Settings, get_settings

PROXY_PREFLIGHT_PATH = "/health"
PROXY_PREFLIGHT_TIMEOUT_SECONDS = 1.5
SERVER_GRACEFUL_SHUTDOWN_SECONDS = 5


def _load_env_template() -> str:
    """Load the canonical root env template from package resources or source."""
    import importlib.resources

    packaged = importlib.resources.files("cli").joinpath("env.example")
    if packaged.is_file():
        return packaged.read_text("utf-8")

    source_template = Path(__file__).resolve().parents[1] / ".env.example"
    if source_template.is_file():
        return source_template.read_text(encoding="utf-8")

    raise FileNotFoundError("Could not find bundled or source .env.example template.")


def serve() -> None:
    """Start the FastAPI server (registered as `fcc-server` script)."""
    opened_admin_browser = False
    try:
        try:
            while True:
                _migrate_legacy_env_if_missing()
                settings = get_settings()
                if not _run_supervised_server(
                    settings, open_admin_browser=not opened_admin_browser
                ):
                    return
                opened_admin_browser = True
                get_settings.cache_clear()
        except KeyboardInterrupt:
            return
    finally:
        kill_all_best_effort()


def dispatch() -> None:
    """Dispatch a `fcc <subcommand> [args...]` invocation.

    Recognises module-registered CLI subcommands (via
    ``cli.module_cli.collect_cli_commands``) and built-in dispatch
    commands (``init``, ``serve``, ``claude``, ``codex``). Unknown
    subcommands print the available list and exit 2.
    """

    from cli.module_cli import collect_cli_commands

    args = sys.argv[1:]
    subcommand = args[0] if args else None

    if subcommand is None or subcommand in {"-h", "--help", "help"}:
        _print_dispatch_help()
        return

    if subcommand == "init":
        init()
        return
    if subcommand == "serve":
        serve()
        return
    if subcommand == "claude":
        launch_claude(args[1:])
        return
    if subcommand == "codex":
        launch_codex(args[1:])
        return

    for command in collect_cli_commands():
        if command.name == subcommand:
            raise SystemExit(command.handler(args[1:]))

    print(f"Unknown fcc subcommand: {subcommand}", file=sys.stderr)
    _print_dispatch_help(to_stderr=True)
    raise SystemExit(2)


def _print_dispatch_help(*, to_stderr: bool = False) -> None:
    """Print the list of built-in + module-registered fcc subcommands."""

    from cli.module_cli import collect_cli_commands

    out = sys.stderr if to_stderr else sys.stdout
    print("Usage: fcc <subcommand> [args...]", file=out)
    print("", file=out)
    print("Built-in subcommands:", file=out)
    print("  init    Scaffold ~/.fcc/.env from the bundled template.", file=out)
    print("  serve   Start the FastAPI proxy (alias for `fcc-server`).", file=out)
    print("  claude  Launch Claude Code pointed at this proxy.", file=out)
    print("  codex   Launch Codex CLI pointed at this proxy.", file=out)

    module_commands = collect_cli_commands()
    if module_commands:
        print("", file=out)
        print("Module subcommands:", file=out)
        for command in module_commands:
            print(f"  {command.name:<8} {command.help}", file=out)


def _admin_browser_open_enabled() -> bool:
    """Whether to open /admin when the server becomes reachable (FCC_OPEN_BROWSER).

    Defaults to OFF so fcc-server does not steal focus to the user's default
    browser on every launch. Operators who want the old behavior can set
    ``FCC_OPEN_BROWSER=true`` (or ``1``/``yes``) in ``~/.fcc/.env``.
    """

    raw = os.environ.get("FCC_OPEN_BROWSER", "false").strip().lower()
    return raw not in {"", "0", "false", "no"}


def _schedule_open_admin_browser(settings: Settings) -> None:
    """After /health succeeds, open the admin UI in the default browser (daemon thread)."""

    if not _admin_browser_open_enabled():
        return

    admin_url = local_admin_url(settings)
    proxy_root_url = local_proxy_root_url(settings)

    def open_when_ready() -> None:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if _preflight_proxy(proxy_root_url) is None:
                webbrowser.open(admin_url)
                return
            time.sleep(0.15)

    threading.Thread(
        target=open_when_ready, name="fcc-open-admin-browser", daemon=True
    ).start()


def _run_supervised_server(settings: Settings, *, open_admin_browser: bool) -> bool:
    """Run one uvicorn server instance; return whether admin requested restart."""

    restart_requested = False
    server_holder: dict[str, uvicorn.Server] = {}

    def request_restart() -> None:
        nonlocal restart_requested
        restart_requested = True
        if server := server_holder.get("server"):
            server.should_exit = True

    app = create_app(lifespan_enabled=False)
    app.state.admin_restart_callback = request_restart
    asgi_app = GracefulLifespanApp(app)
    config = uvicorn.Config(
        asgi_app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        timeout_graceful_shutdown=SERVER_GRACEFUL_SHUTDOWN_SECONDS,
    )
    server = uvicorn.Server(config)
    server_holder["server"] = server
    if open_admin_browser:
        _schedule_open_admin_browser(settings)
    server.run()
    return restart_requested


def init() -> None:
    """Scaffold config at ~/.fcc/.env (registered as `fcc-init`)."""
    config_dir = config_dir_path()
    env_file = managed_env_path()

    migrated_from = _migrate_legacy_env_if_missing()
    if migrated_from is not None:
        print(f"Config migrated from {migrated_from} to {env_file}")
        print(
            "Edit it to set your API keys and model preferences, then run: fcc-server"
        )
        return

    if env_file.exists():
        print(f"Config already exists at {env_file}")
        print("Delete it first if you want to reset to defaults.")
        return

    config_dir.mkdir(parents=True, exist_ok=True)
    template = _load_env_template()
    env_file.write_text(template, encoding="utf-8")
    print(f"Config created at {env_file}")
    print("Edit it to set your API keys and model preferences, then run: fcc-server")


def _migrate_legacy_env_if_missing() -> Path | None:
    """Copy a legacy user env into the managed config path when absent."""

    env_file = managed_env_path()
    if env_file.exists():
        return None

    # TODO: Remove after the ~/.fcc/.env migration has had a release cycle.
    for legacy_env in legacy_env_paths():
        if not legacy_env.is_file():
            continue
        env_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(legacy_env, env_file)
        return legacy_env

    return None


def _resolve_repo_root() -> str:
    """Return the current repository root or the current working directory."""
    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        if (path / ".git").exists():
            return str(path)
    return str(cwd)


def _claude_child_env(
    settings: Settings, base_env: Mapping[str, str]
) -> dict[str, str]:
    """Return a Claude Code environment that targets this proxy."""

    return CLAUDE_CLI_ADAPTER.build_launcher_env(
        proxy_root_url=local_proxy_root_url(settings),
        auth_token=settings.anthropic_auth_token,
        base_env=base_env,
        repo_path=_resolve_repo_root(),
    )


def _preflight_proxy(proxy_root_url: str) -> str | None:
    """Return an error message when the local proxy health check is unreachable."""

    url = f"{proxy_root_url.rstrip('/')}{PROXY_PREFLIGHT_PATH}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=PROXY_PREFLIGHT_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
    except HTTPError as exc:
        return f"returned HTTP {exc.code}"
    except URLError as exc:
        return str(exc.reason)
    except OSError as exc:
        return str(exc)

    if not 200 <= status_code < 300:
        return f"returned HTTP {status_code}"
    return None


def launch_claude(argv: Sequence[str] | None = None) -> None:
    """Launch Claude Code with Claude Unbound proxy environment variables."""

    _launch_client_cli(CLAUDE_CLI_ADAPTER, argv)


def launch_codex(argv: Sequence[str] | None = None) -> None:
    """Launch Codex CLI with Claude Unbound proxy configuration."""

    _launch_client_cli(CODEX_CLI_ADAPTER, argv)


def _launch_client_cli(
    adapter: ClientCliAdapter, argv: Sequence[str] | None = None
) -> None:
    """Launch a client CLI with Claude Unbound proxy environment variables."""

    settings = get_settings()
    proxy_root_url = local_proxy_root_url(settings)
    if error := _preflight_proxy(proxy_root_url):
        print(
            f"Claude Unbound proxy is not reachable at {proxy_root_url}: {error}",
            file=sys.stderr,
        )
        print("Start it in another terminal with: fcc-server", file=sys.stderr)
        raise SystemExit(1)

    args = list(sys.argv[1:] if argv is None else argv)
    binary_name = adapter.get_launcher_binary_name(settings)
    client_command = shutil.which(binary_name)
    if client_command is None:
        print(
            f"Could not find {adapter.display_name} command: {binary_name}",
            file=sys.stderr,
        )
        print(adapter.install_hint, file=sys.stderr)
        raise SystemExit(127)

    command = adapter.build_launcher_command(
        binary_path=client_command,
        argv=args,
        settings=settings,
        proxy_root_url=proxy_root_url,
    )
    catalog_args = _codex_model_catalog_config_args(adapter, proxy_root_url, settings)
    if catalog_args:
        command = [command[0], *catalog_args, *command[1:]]
    env = adapter.build_launcher_env(
        proxy_root_url=proxy_root_url,
        auth_token=settings.anthropic_auth_token,
        base_env=os.environ,
        repo_path=_resolve_repo_root(),
    )
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(command, env=env)
        if process.pid:
            register_pid(process.pid)
        return_code = process.wait()
    except FileNotFoundError:
        print(
            f"Could not find {adapter.display_name} command: {binary_name}",
            file=sys.stderr,
        )
        print(adapter.install_hint, file=sys.stderr)
        raise SystemExit(127) from None
    except KeyboardInterrupt:
        if process is not None and process.pid:
            kill_pid_tree_best_effort(process.pid)
            process.wait()
        raise
    finally:
        if process is not None and process.pid:
            unregister_pid(process.pid)

    raise SystemExit(return_code)


def _codex_model_catalog_config_args(
    adapter: ClientCliAdapter, proxy_root_url: str, settings: Settings
) -> list[str]:
    if adapter.id != CODEX_CLI_ADAPTER.id:
        return []

    try:
        models_response = _fetch_proxy_models_response(
            proxy_root_url, settings.anthropic_auth_token
        )
        catalog = build_codex_model_catalog(models_response)
        models = catalog.get("models")
        if not isinstance(models, list) or not models:
            print(
                "Claude Unbound warning: Codex model catalog is empty; "
                "launching without model picker catalog.",
                file=sys.stderr,
            )
            return []
        catalog_path = codex_model_catalog_path()
        write_codex_model_catalog(catalog_path, catalog)
    except Exception as exc:
        print(
            "Claude Unbound warning: could not prepare Codex model catalog "
            f"({exc}); launching without model picker catalog.",
            file=sys.stderr,
        )
        return []

    return CODEX_CLI_ADAPTER.build_model_catalog_config_args(str(catalog_path))


def _fetch_proxy_models_response(
    proxy_root_url: str, auth_token: str
) -> dict[str, object]:
    url = f"{proxy_root_url.rstrip('/')}/v1/models"
    headers: dict[str, str] = {}
    if token := auth_token.strip():
        headers["X-API-Key"] = token

    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=PROXY_PREFLIGHT_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("model list response was not a JSON object")
    return payload
