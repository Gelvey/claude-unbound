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
