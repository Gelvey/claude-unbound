"""Custom module discovery, loading, and lifecycle management."""

from __future__ import annotations

import contextlib
import importlib.util
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import dotenv_values
from loguru import logger

from config.paths import modules_dir_path

from .contracts import Module
from .errors import ModuleLoadError, ModuleRegistrationError

if TYPE_CHECKING:
    from fastapi import FastAPI

    from config.settings import Settings


_MODULE_FILE_PREFIX = "claude_unbound_module_"


def _dotenv_value(key: str) -> str | None:
    """Read a raw value from the same .env files Pydantic Settings will use.

    Later ``get_settings()`` re-reads these files through Pydantic; this
    helper gives us ``modules_enabled`` / ``modules_dir`` before the full
    model (and its provider-id validation) is instantiated.
    """

    from config.settings import _env_files

    for env_file in _env_files():
        if not env_file.is_file():
            continue
        try:
            values = dotenv_values(env_file)
        except OSError:
            continue
        if key in values:
            value = values[key]
            return "" if value is None else value
    return None


def _modules_enabled_pre() -> bool:
    """Return whether module loading requested before Settings exists."""

    value = _dotenv_value("FCC_MODULES_ENABLED")
    if value is None:
        value = os.environ.get("FCC_MODULES_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in {"", "false", "0", "no", "off"}


def _modules_dir_pre() -> Path:
    """Return the modules directory before Settings exists."""

    value = _dotenv_value("FCC_MODULES_DIR") or os.environ.get("FCC_MODULES_DIR")
    if value:
        return Path(os.path.expanduser(value))
    return modules_dir_path()


def _path_to_module_name(path: Path) -> str:
    """Create a deterministic, unique module name for a file/package path."""

    escaped = path.resolve().as_posix().replace("/", "_").replace(".", "_")
    return f"{_MODULE_FILE_PREFIX}{escaped}"


def _is_module_path(path: Path) -> bool:
    """Return True for loadable module files/packages."""

    if path.name.startswith("_"):
        return False
    if not path.exists():
        return False
    return (path.is_file() and path.suffix == ".py") or (
        path.is_dir() and (path / "__init__.py").is_file()
    )


def _discover_module_paths(modules_dir: Path) -> list[Path]:
    """Discover candidate top-level module files and packages."""

    if not modules_dir.is_dir():
        return []

    candidates = [entry for entry in modules_dir.iterdir() if _is_module_path(entry)]
    candidates.sort(key=lambda p: p.name)
    return candidates


def _load_python_module(path: Path) -> Any:
    """Import a Python file or package from an arbitrary path."""

    module_name = _path_to_module_name(path)
    if path.is_file():
        spec = importlib.util.spec_from_file_location(module_name, path)
    else:
        init_file = path / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            module_name, init_file, submodule_search_locations=[str(path)]
        )

    if spec is None or spec.loader is None:
        raise ModuleLoadError(f"Cannot create module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_module(
    module: Any,
    app: FastAPI,
    settings: Settings | None,
) -> Module:
    """Return the Module defined by an imported file/package."""

    if hasattr(module, "setup_module"):
        setup = module.setup_module
        if not callable(setup):
            raise ModuleLoadError(f"setup_module in {module.__name__} is not callable")
        result = setup(app, settings)
        if result is None:
            raise ModuleLoadError(f"setup_module in {module.__name__} returned None")
        return result

    if hasattr(module, "FCC_MODULE"):
        return module.FCC_MODULE

    raise ModuleLoadError(
        f"Module {module.__name__} has no FCC_MODULE or setup_module attribute"
    )


def _log_error(settings: Settings | None, message: str, exc: Exception) -> None:
    """Log a module error, respecting the verbose-errorback setting."""

    verbose = settings.log_api_error_tracebacks if settings is not None else False
    if verbose:
        logger.opt(exception=exc).error(message)
    else:
        logger.error("{}: exc_type={}", message, type(exc).__name__)


class ModuleManager:
    """Owns loaded custom modules and their runtime hooks."""

    def __init__(self) -> None:
        self.modules: list[Module] = []
        self.failed: list[str] = []
        # Track contributions so tests can reset global state.
        self._provider_ids: list[str] = []
        self._router_count: int = 0
        self._message_intercepts: list[Any] = []
        self._optimization_handlers: list[Any] = []
        self._messaging_platforms: list[str] = []

    @classmethod
    def load_for_app(
        cls,
        app: FastAPI,
        settings: Settings | None = None,
    ) -> ModuleManager:
        """Discover, import, and register modules for the given app."""

        manager = cls()

        if not _modules_enabled_pre():
            logger.debug("Custom modules disabled via FCC_MODULES_ENABLED")
            return manager

        modules_dir = _modules_dir_pre()
        if not modules_dir.is_dir():
            logger.debug("Custom modules directory does not exist: {}", modules_dir)
            return manager

        for path in _discover_module_paths(modules_dir):
            module = manager._load_one(path, app, settings)
            if module is None:
                label = path.stem if path.is_file() else path.name
                manager.failed.append(label)
                continue

            manager.modules.append(module)
            manager._register(module, app, settings)

        logger.info(
            "Custom modules loaded: {} success, {} failed (from {})",
            len(manager.modules),
            len(manager.failed),
            modules_dir,
        )
        return manager

    def _load_one(
        self,
        path: Path,
        app: FastAPI,
        settings: Settings | None,
    ) -> Module | None:
        """Import a single path and return its Module, or None on failure."""

        label = path.stem if path.is_file() else path.name
        try:
            raw_module = _load_python_module(path)
        except Exception as exc:
            _log_error(settings, f"Failed to import module '{label}'", exc)
            return None

        try:
            module = _extract_module(raw_module, app, settings)
        except Exception as exc:
            _log_error(settings, f"Failed to configure module '{label}'", exc)
            return None

        if not isinstance(module, Module):
            logger.error(
                "Module '{}' FCC_MODULE/setup_module returned type {}, expected Module",
                label,
                type(module).__name__,
            )
            return None

        return module

    def _register(
        self,
        module: Module,
        app: FastAPI,
        settings: Settings | None,
    ) -> None:
        """Register a loaded module's contributions into runtime surfaces."""

        self._register_providers(module, settings)
        self._register_routers(module, app, settings)
        self._register_pipeline(module, settings)
        self._register_messaging_platforms(module, settings)

    def _register_providers(self, module: Module, settings: Settings | None) -> None:
        if not module.provider_descriptors and not module.provider_factories:
            return

        from config.provider_catalog import PROVIDER_CATALOG
        from config.provider_ids import SUPPORTED_PROVIDER_IDS
        from providers.registry import PROVIDER_FACTORIES

        for provider_id in module.provider_descriptors:
            descriptor = module.provider_descriptors[provider_id]
            try:
                if provider_id in PROVIDER_CATALOG:
                    raise ModuleRegistrationError(
                        f"Provider '{provider_id}' is already registered",
                        module_name=module.name,
                        surface="provider_descriptors",
                    )
                PROVIDER_CATALOG[provider_id] = descriptor
                if provider_id not in SUPPORTED_PROVIDER_IDS:
                    SUPPORTED_PROVIDER_IDS.append(provider_id)
                self._provider_ids.append(provider_id)
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register provider '{provider_id}'",
                    exc,
                )

        for provider_id, factory in module.provider_factories.items():
            try:
                if provider_id in PROVIDER_FACTORIES:
                    raise ModuleRegistrationError(
                        f"Provider factory '{provider_id}' is already registered",
                        module_name=module.name,
                        surface="provider_factories",
                    )
                PROVIDER_FACTORIES[provider_id] = factory
                if provider_id not in SUPPORTED_PROVIDER_IDS:
                    SUPPORTED_PROVIDER_IDS.append(provider_id)
                if provider_id not in self._provider_ids:
                    self._provider_ids.append(provider_id)
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register provider factory '{provider_id}'",
                    exc,
                )

    def _register_routers(
        self, module: Module, app: FastAPI, settings: Settings | None
    ) -> None:
        for router in module.routers:
            try:
                app.include_router(router)
                self._router_count += 1
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register router",
                    exc,
                )

    def _register_pipeline(self, module: Module, settings: Settings | None) -> None:
        if module.message_intercepts:
            from api.request_pipeline import add_message_intercepts

            try:
                add_message_intercepts(module.message_intercepts)
                self._message_intercepts.extend(module.message_intercepts)
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register message intercepts",
                    exc,
                )

        if module.optimization_handlers:
            from api.optimization_handlers import OPTIMIZATION_HANDLERS

            try:
                OPTIMIZATION_HANDLERS.extend(module.optimization_handlers)
                self._optimization_handlers.extend(module.optimization_handlers)
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register optimization handlers",
                    exc,
                )

    def _register_messaging_platforms(
        self, module: Module, settings: Settings | None
    ) -> None:
        if not module.messaging_platform_factories:
            return

        from messaging.platforms.factory import register_messaging_platform

        for name, factory in module.messaging_platform_factories.items():
            try:
                register_messaging_platform(name, factory)
                self._messaging_platforms.append(name)
            except Exception as exc:
                _log_error(
                    settings,
                    f"Module '{module.name}' could not register messaging platform '{name}'",
                    exc,
                )

    async def run_startup(self, app: FastAPI, settings: Settings) -> None:
        """Run startup hooks for all loaded modules."""

        for module in self.modules:
            for hook in module.startup_hooks:
                try:
                    await hook(app, settings)
                except Exception as exc:
                    _log_error(
                        settings,
                        f"Module '{module.name}' startup hook failed",
                        exc,
                    )

    async def run_shutdown(self, app: FastAPI, settings: Settings) -> None:
        """Run shutdown hooks for all loaded modules in reverse order."""

        for module in reversed(self.modules):
            for hook in module.shutdown_hooks:
                try:
                    await hook(app, settings)
                except Exception as exc:
                    _log_error(
                        settings,
                        f"Module '{module.name}' shutdown hook failed",
                        exc,
                    )

    def reset(self) -> None:
        """Remove all module contributions from global state (tests only)."""

        from config.provider_catalog import PROVIDER_CATALOG
        from config.provider_ids import SUPPORTED_PROVIDER_IDS
        from providers.registry import PROVIDER_FACTORIES

        for provider_id in self._provider_ids:
            PROVIDER_CATALOG.pop(provider_id, None)
            PROVIDER_FACTORIES.pop(provider_id, None)
            with contextlib.suppress(ValueError):
                SUPPORTED_PROVIDER_IDS.remove(provider_id)

        if self._message_intercepts:
            from api.request_pipeline import remove_message_intercepts

            remove_message_intercepts(self._message_intercepts)

        if self._optimization_handlers:
            from api.optimization_handlers import OPTIMIZATION_HANDLERS

            for handler in self._optimization_handlers:
                with contextlib.suppress(ValueError):
                    OPTIMIZATION_HANDLERS.remove(handler)

        if self._messaging_platforms:
            from messaging.platforms.factory import unregister_messaging_platforms

            unregister_messaging_platforms(self._messaging_platforms)

        self.modules.clear()
        self.failed.clear()
        self._provider_ids.clear()
        self._router_count = 0
        self._message_intercepts.clear()
        self._optimization_handlers.clear()
        self._messaging_platforms.clear()
