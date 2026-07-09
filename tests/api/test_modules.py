"""Tests for the custom module loader and registration surfaces."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.modules.loader import ModuleManager
from config.provider_catalog import SUPPORTED_PROVIDER_IDS


@pytest.fixture
def module_manager_factory(modules_dir: Path):
    """Return a factory that loads modules from the temp dir into a fresh app."""

    def _make():
        # Clear environment-sensitive Settings cache so the manager sees the
        # temp directory and enabled flag from the modules_dir fixture.
        from config.settings import get_settings

        get_settings.cache_clear()
        app = FastAPI()
        manager = ModuleManager.load_for_app(app, settings=None)
        return app, manager

    return _make


def _write_module(modules_dir: Path, name: str, source: str) -> Path:
    """Write a module source file under the temp directory."""

    path = modules_dir / f"{name}.py"
    path.write_text(textwrap.dedent(source))
    return path


def test_discovery_ignores_private_and_non_python(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    modules_dir.joinpath("_private.py").write_text("FCC_MODULE = None")
    modules_dir.joinpath("__pycache__").mkdir()
    modules_dir.joinpath("__pycache__").joinpath("junk.py").write_text("")
    modules_dir.joinpath("ignored.txt").write_text("not python")
    modules_dir.joinpath("valid.py").write_text(
        'from api.modules import module\nFCC_MODULE = module("valid")'
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert [m.name for m in manager.modules] == ["valid"]
    assert not manager.failed


def test_load_failure_logs_and_continues(
    modules_dir: Path, module_manager_factory, reset_loaded_modules, caplog
):
    _write_module(
        modules_dir,
        "good",
        """
        from api.modules import module
        FCC_MODULE = module("good")
    """,
    )
    _write_module(modules_dir, "broken", "this is not valid python {{\n")

    with caplog.at_level("ERROR"):
        _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert [m.name for m in manager.modules] == ["good"]
    assert "broken" in manager.failed
    assert any("broken" in r.message for r in caplog.records)


def test_module_router_registered(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "routes",
        """
        from fastapi import APIRouter
        from api.modules import Module

        router = APIRouter()

        @router.get("/hello-module")
        def hello():
            return {"hello": "module"}

        FCC_MODULE = Module(name="routes", routers=[router])
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    with TestClient(_app) as client:
        response = client.get("/hello-module")

    assert response.status_code == 200
    assert response.json() == {"hello": "module"}


def test_module_provider_registered(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "my_provider",
        """
        from config.provider_catalog import ProviderDescriptor
        from providers.base import BaseProvider, ProviderConfig
        from api.modules import Module

        def factory(config: ProviderConfig, settings) -> BaseProvider:
            raise RuntimeError("not meant to be instantiated in this test")

        descriptor = ProviderDescriptor(
            provider_id="my_provider",
            transport_type="openai_chat",
            capabilities=(),
        )

        FCC_MODULE = Module(
            name="my_provider",
            provider_descriptors={"my_provider": descriptor},
            provider_factories={"my_provider": factory},
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert "my_provider" in SUPPORTED_PROVIDER_IDS


def test_modules_disabled_skips_discovery(modules_dir: Path, monkeypatch):
    monkeypatch.setenv("FCC_MODULES_ENABLED", "false")
    modules_dir.joinpath("would_fail.py").write_text("not valid {{\n")

    from config.settings import get_settings

    get_settings.cache_clear()
    _app = FastAPI()
    manager = ModuleManager.load_for_app(_app, settings=None)

    assert not manager.modules
    assert not manager.failed


def test_setup_module_function(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "setup_fn",
        """
        from fastapi import APIRouter
        from api.modules import Module

        router = APIRouter()

        @router.get("/setup-fn")
        def ping():
            return {"ok": True}

        def setup_module(app, settings):
            return Module(name="setup_fn", routers=[router])
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert [m.name for m in manager.modules] == ["setup_fn"]

    with TestClient(_app) as client:
        response = client.get("/setup-fn")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_module_lifecycle_hooks(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    marker = modules_dir / "lifecycle_marker.txt"
    marker_path = str(marker)
    source = f"""
        from api.modules import Module

        async def startup(app, settings):
            with open({marker_path!r}, "w") as f:
                f.write("startup")

        async def shutdown(app, settings):
            with open({marker_path!r}, "a") as f:
                f.write("|shutdown")

        FCC_MODULE = Module(
            name="lifecycle",
            startup_hooks=[startup],
            shutdown_hooks=[shutdown],
        )
    """
    _write_module(modules_dir, "lifecycle", source)

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    await manager.run_startup(_app, None)
    await manager.run_shutdown(_app, None)

    assert marker.read_text() == "startup|shutdown"


# ---------------------------------------------------------------------------
# B1: Atomic provider registration — descriptor+factory are both required
# ---------------------------------------------------------------------------


def test_provider_registration_is_atomic_when_descriptor_missing(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    """If descriptor is missing, neither descriptor nor factory is registered."""

    _write_module(
        modules_dir,
        "half_provider",
        """
        from providers.base import BaseProvider, ProviderConfig
        from api.modules import Module

        def factory(config: ProviderConfig, settings) -> BaseProvider:
            raise RuntimeError("not meant to be instantiated")

        FCC_MODULE = Module(
            name="half_provider",
            provider_factories={"only_factory": factory},
        )
    """,
    )

    from config.provider_catalog import PROVIDER_CATALOG
    from providers.registry import PROVIDER_FACTORIES

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert "only_factory" not in PROVIDER_CATALOG
    assert "only_factory" not in PROVIDER_FACTORIES
    assert "only_factory" not in SUPPORTED_PROVIDER_IDS


def test_provider_registration_is_atomic_when_factory_missing(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    """If factory is missing, neither descriptor nor factory is registered."""

    _write_module(
        modules_dir,
        "half_provider_2",
        """
        from config.provider_catalog import ProviderDescriptor
        from api.modules import Module

        descriptor = ProviderDescriptor(
            provider_id="only_descriptor",
            transport_type="openai_chat",
            capabilities=(),
        )
        FCC_MODULE = Module(
            name="half_provider_2",
            provider_descriptors={"only_descriptor": descriptor},
        )
    """,
    )

    from config.provider_catalog import PROVIDER_CATALOG
    from providers.registry import PROVIDER_FACTORIES

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert "only_descriptor" not in PROVIDER_CATALOG
    assert "only_descriptor" not in PROVIDER_FACTORIES
    assert "only_descriptor" not in SUPPORTED_PROVIDER_IDS


# ---------------------------------------------------------------------------
# N1: HTTP Middleware
# ---------------------------------------------------------------------------


def test_module_middleware_sets_response_header(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "mw_module",
        """
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from api.modules import Module

        class HeaderMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                response = await call_next(request)
                response.headers["X-Module-Mw"] = "yes"
                return response

        FCC_MODULE = Module(name="mw_module", middlewares=[HeaderMiddleware])
    """,
    )

    app = FastAPI()
    app.get("/mw-check")(lambda: {"ok": True})
    manager = ModuleManager.load_for_app(app, settings=None)
    reset_loaded_modules(manager)
    # Phase 2: register the trace middleware then the module middlewares.
    app.middleware("http")(lambda request, call_next: call_next(request))
    manager.apply_middlewares(app)

    with TestClient(app) as client:
        response = client.get("/mw-check")

    assert response.status_code == 200
    assert response.headers.get("X-Module-Mw") == "yes"


# ---------------------------------------------------------------------------
# N2: System directive
# ---------------------------------------------------------------------------


def test_module_system_directive_appended(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    from api.request_pipeline import get_module_system_directives

    _write_module(
        modules_dir,
        "directive_module",
        """
        from api.modules import Module
        FCC_MODULE = Module(
            name="directive_module",
            system_directives=["plugin:hello", "plugin:world"],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    directives = get_module_system_directives()
    assert "plugin:hello" in directives
    assert "plugin:world" in directives


# ---------------------------------------------------------------------------
# N3: Custom token counter
# ---------------------------------------------------------------------------


def test_module_token_counter_overrides_default(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "tc_module",
        """
        from api.modules import Module

        def counter(messages, system, tools):
            return 42

        FCC_MODULE = Module(name="tc_module", token_counter_override=counter)
    """,
    )

    from api.request_pipeline import get_module_token_counter

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    counter = get_module_token_counter()
    assert counter is not None
    assert counter([], None, []) == 42


# ---------------------------------------------------------------------------
# N4: Reroute strategy
# ---------------------------------------------------------------------------


def test_module_reroute_strategy_registered(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "reroute_module",
        """
        from api.modules import Module

        def reroute(req, settings):
            return None

        FCC_MODULE = Module(name="reroute_module", reroute_strategies=[reroute])
    """,
    )

    from api.request_pipeline import get_reroute_strategies

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    strategies = get_reroute_strategies()
    assert any(getattr(s, "__name__", "") == "reroute" for s in strategies)


# ---------------------------------------------------------------------------
# N5: Admin tab
# ---------------------------------------------------------------------------


def test_module_admin_tab_registered_and_served(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "tab_module",
        """
        from api.modules import Module, AdminTabSpec
        FCC_MODULE = Module(
            name="tab_module",
            admin_tabs=[
                AdminTabSpec(
                    id="module_tab",
                    label="Module",
                    title="Module Tab",
                    html="<p>hi</p>",
                    mount_js="window.__module_tab_loaded = true;",
                )
            ],
        )
    """,
    )

    app, manager = module_manager_factory()
    reset_loaded_modules(manager)
    app.include_router(__import__("api.admin_routes", fromlist=["router"]).router)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/admin/api/modules/tabs")

    assert response.status_code == 200
    body = response.json()
    assert len(body["tabs"]) == 1
    assert body["tabs"][0]["id"] == "module_tab"
    assert body["tabs"][0]["label"] == "Module"


# ---------------------------------------------------------------------------
# N6: Module Settings
# ---------------------------------------------------------------------------


def test_module_setting_reads_from_env(
    modules_dir: Path, module_manager_factory, reset_loaded_modules, monkeypatch
):
    monkeypatch.setenv("MY_PLUGIN_TOKEN", "secret123")

    _write_module(
        modules_dir,
        "settings_module",
        """
        from api.modules import Module, ModuleSettingSpec
        FCC_MODULE = Module(
            name="settings_module",
            settings_fields=[
                ModuleSettingSpec(
                    alias="MY_PLUGIN_TOKEN",
                    type=str,
                    default="",
                    description="API token",
                )
            ],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    from config.module_settings import get_module_settings

    settings = get_module_settings()
    token = getattr(settings, "my_plugin_token")  # noqa: B009
    assert token == "secret123"


# ---------------------------------------------------------------------------
# N7: CLI subcommand
# ---------------------------------------------------------------------------


def test_module_cli_command_collected(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "cli_module",
        """
        from api.modules import Module, ModuleCliCommand

        def mycmd(argv):
            print("ran")
            return 0

        FCC_MODULE = Module(
            name="cli_module",
            cli_commands=[
                ModuleCliCommand(
                    name="mycmd", help="My custom command", handler=mycmd
                )
            ],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    assert any(c.name == "mycmd" for c in manager.cli_commands())


def test_module_cli_command_handler_invoked(
    modules_dir: Path, module_manager_factory, reset_loaded_modules, capsys
):
    _write_module(
        modules_dir,
        "cli_handler_module",
        """
        from api.modules import Module, ModuleCliCommand

        def hello(argv):
            print("hi from module")
            return 7

        FCC_MODULE = Module(
            name="cli_handler_module",
            cli_commands=[
                ModuleCliCommand(
                    name="hello", help="Says hi", handler=hello
                )
            ],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    from cli.module_cli import collect_cli_commands

    cmds = collect_cli_commands()
    matching = next(c for c in cmds if c.name == "hello")
    rc = matching.handler(["arg1"])
    captured = capsys.readouterr()
    assert rc == 7
    assert "hi from module" in captured.out


# ---------------------------------------------------------------------------
# N8: MCP server registration
# ---------------------------------------------------------------------------


def test_module_mcp_server_registered(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    from api.mcp_config import McpBackend

    _write_module(
        modules_dir,
        "mcp_module",
        """
        from api.mcp_config import McpBackend
        from api.modules import Module, ModuleMcpServer
        backend = McpBackend(
            name="x",
            type="stdio",
            port=19001,
            command="echo",
            args=[],
        )
        FCC_MODULE = Module(
            name="mcp_module",
            mcp_servers=[ModuleMcpServer(name="x", backend=backend)],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    servers = manager.mcp_servers()
    assert len(servers) == 1
    assert servers[0].name == "x"
    assert isinstance(servers[0].backend, McpBackend)


# ---------------------------------------------------------------------------
# N9: Trace listener
# ---------------------------------------------------------------------------


def test_module_trace_listener_invoked(
    modules_dir: Path, module_manager_factory, reset_loaded_modules
):
    _write_module(
        modules_dir,
        "trace_module",
        """
        from api.modules import Module

        events = []

        def listener(stage, event, source, fields):
            events.append((stage, event, source))

        listener.events = events
        FCC_MODULE = Module(name="trace_module", trace_listeners=[listener])
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    from core.trace import trace_event

    trace_event(stage="test", event="pytest.event", source="test", x=1)

    # Find the listener via the loaded module.
    from core.trace import get_trace_listeners

    listeners = get_trace_listeners()
    matching = next(
        listener
        for listener in listeners
        if getattr(listener, "__name__", "") == "listener"
    )
    recorded = getattr(matching, "events")  # noqa: B009
    assert any(ev[1] == "pytest.event" for ev in recorded)


# ---------------------------------------------------------------------------
# Module dispatch: built-in `fcc` subcommand
# ---------------------------------------------------------------------------


def test_fcc_dispatch_help_prints_subcommands(
    modules_dir: Path, module_manager_factory, reset_loaded_modules, capsys
):
    _write_module(
        modules_dir,
        "dispatch_module",
        """
        from api.modules import Module, ModuleCliCommand

        def demo(argv):
            return 0

        FCC_MODULE = Module(
            name="dispatch_module",
            cli_commands=[
                ModuleCliCommand(name="demo", help="Demo command", handler=demo)
            ],
        )
    """,
    )

    _app, manager = module_manager_factory()
    reset_loaded_modules(manager)

    import sys as _sys

    saved = _sys.argv
    try:
        _sys.argv = ["fcc"]
        from cli.entrypoints import _print_dispatch_help

        _print_dispatch_help()
    finally:
        _sys.argv = saved

    out = capsys.readouterr().out
    assert "serve" in out
    assert "init" in out
    assert "demo" in out
