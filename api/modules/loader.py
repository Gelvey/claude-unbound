"""Custom module discovery, loading, and lifecycle management."""

from __future__ import annotations

import contextlib
import importlib.util
import os
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import dotenv_values
from loguru import logger

from config.paths import modules_dir_path

from .contracts import (
    Module,
    ModuleCliCommand,
    ModuleMcpServer,
    ModuleSettingSpec,
)
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


def _load_verbosity_pre() -> bool:
    """Return whether module-load failures should print full tracebacks.

    Reads the same env key as :class:`config.settings.Settings` so operators
    who enabled verbose error logging for the rest of the app also see it for
    module load failures — even though Settings has not been built yet.
    """

    value = _dotenv_value("LOG_API_ERROR_TRACEBACKS")
    if value is None:
        value = os.environ.get("LOG_API_ERROR_TRACEBACKS")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _log_error(message: str, exc: Exception, *, verbose: bool) -> None:
    """Log a module error, full traceback when ``verbose`` is True."""

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
        self._reroute_strategies: list[Any] = []
        self._system_directives: list[str] = []
        self._messaging_platforms: list[str] = []
        self._admin_tabs: list[Any] = []
        self._settings_fields: list[ModuleSettingSpec] = []
        self._cli_commands: list[ModuleCliCommand] = []
        self._mcp_servers: list[ModuleMcpServer] = []
        self._trace_listeners: list[Any] = []
        self._middlewares: list[type] = []
        # Single token-counter slot (last-registered wins).
        self._token_counter: Any = None

    @classmethod
    def load_for_app(
        cls,
        app: FastAPI,
        settings: Settings | None = None,
    ) -> ModuleManager:
        """Phase 1: discover, import, and register module contributions.

        Middlewares are stashed in ``self._middlewares`` and must be applied
        later via :meth:`apply_middlewares` after the trace-correlation
        middleware has been registered on the app. See ``api/app.py``.
        """

        manager = cls()
        verbose = _load_verbosity_pre()

        if not _modules_enabled_pre():
            logger.debug("Custom modules disabled via FCC_MODULES_ENABLED")
            return manager

        modules_dir = _modules_dir_pre()
        if not modules_dir.is_dir():
            logger.debug("Custom modules directory does not exist: {}", modules_dir)
            return manager

        for path in _discover_module_paths(modules_dir):
            module = manager._load_one(path, app, settings, verbose=verbose)
            if module is None:
                label = path.stem if path.is_file() else path.name
                manager.failed.append(label)
                continue

            manager.modules.append(module)
            manager._register(module, app, settings)

        # Phase 1: token counter, system directives, and trace listeners are
        # activated immediately so /v1/messages sees them. Admin tab and CLI
        # command metadata is collected for later surfacing.
        manager._activate_token_counter()
        manager._activate_system_directives()
        manager._activate_trace_listeners()
        manager._publish_admin_tabs(app)
        manager._publish_cli_commands(app)
        manager._publish_mcp_servers(app)
        manager._build_module_settings()

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
        *,
        verbose: bool,
    ) -> Module | None:
        """Import a single path and return its Module, or None on failure."""

        label = path.stem if path.is_file() else path.name
        try:
            raw_module = _load_python_module(path)
        except Exception as exc:
            _log_error(f"Failed to import module '{label}'", exc, verbose=verbose)
            return None

        try:
            module = _extract_module(raw_module, app, settings)
        except Exception as exc:
            _log_error(f"Failed to configure module '{label}'", exc, verbose=verbose)
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
        self._register_middlewares(module)
        self._register_pipeline(module, settings)
        self._register_messaging_platforms(module, settings)
        self._register_admin_tabs(module)
        self._register_settings_fields(module)
        self._register_cli_commands(module)
        self._register_mcp_servers(module)
        self._register_trace_listeners(module)

    def _register_providers(self, module: Module, settings: Settings | None) -> None:
        """Atomically register each provider's descriptor+factory pair.

        Both must be present; if either is missing, the registration is
        rejected as a whole so ``PROVIDER_CATALOG`` and ``PROVIDER_FACTORIES``
        never diverge.
        """

        if not module.provider_descriptors and not module.provider_factories:
            return

        from config.provider_catalog import PROVIDER_CATALOG
        from config.provider_ids import SUPPORTED_PROVIDER_IDS
        from providers.registry import PROVIDER_FACTORIES

        # Union the keys; require both descriptor and factory for each id.
        all_ids = set(module.provider_descriptors) | set(module.provider_factories)
        for provider_id in sorted(all_ids):
            try:
                descriptor = module.provider_descriptors.get(provider_id)
                factory = module.provider_factories.get(provider_id)
                if descriptor is None or factory is None:
                    raise ModuleRegistrationError(
                        f"Provider '{provider_id}' must declare both a descriptor and a factory",
                        module_name=module.name,
                        surface="provider_descriptors",
                    )
                if provider_id in PROVIDER_CATALOG:
                    raise ModuleRegistrationError(
                        f"Provider '{provider_id}' is already registered",
                        module_name=module.name,
                        surface="provider_descriptors",
                    )
                if provider_id in PROVIDER_FACTORIES:
                    raise ModuleRegistrationError(
                        f"Provider factory '{provider_id}' is already registered",
                        module_name=module.name,
                        surface="provider_factories",
                    )
                PROVIDER_CATALOG[provider_id] = descriptor
                PROVIDER_FACTORIES[provider_id] = factory
                if provider_id not in SUPPORTED_PROVIDER_IDS:
                    SUPPORTED_PROVIDER_IDS.append(provider_id)
                self._provider_ids.append(provider_id)
            except Exception as exc:
                _log_error(
                    f"Module '{module.name}' could not register provider '{provider_id}'",
                    exc,
                    verbose=_load_verbosity_pre(),
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
                    f"Module '{module.name}' could not register router",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

    def _register_middlewares(self, module: Module) -> None:
        """Stash middleware classes; they are applied in phase 2."""

        for middleware_class in module.middlewares:
            self._middlewares.append(middleware_class)

    def _register_pipeline(self, module: Module, settings: Settings | None) -> None:
        if module.message_intercepts:
            from api.request_pipeline import add_message_intercepts

            try:
                add_message_intercepts(module.message_intercepts)
                self._message_intercepts.extend(module.message_intercepts)
            except Exception as exc:
                _log_error(
                    f"Module '{module.name}' could not register message intercepts",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

        if module.optimization_handlers:
            from api.optimization_handlers import OPTIMIZATION_HANDLERS

            try:
                OPTIMIZATION_HANDLERS.extend(module.optimization_handlers)
                self._optimization_handlers.extend(module.optimization_handlers)
            except Exception as exc:
                _log_error(
                    f"Module '{module.name}' could not register optimization handlers",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

        if module.reroute_strategies:
            from api.request_pipeline import add_reroute_strategies

            try:
                add_reroute_strategies(module.reroute_strategies)
                self._reroute_strategies.extend(module.reroute_strategies)
            except Exception as exc:
                _log_error(
                    f"Module '{module.name}' could not register reroute strategies",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

        if module.token_counter_override is not None:
            self._token_counter = module.token_counter_override

        if module.system_directives:
            self._system_directives.extend(module.system_directives)

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
                    f"Module '{module.name}' could not register messaging platform '{name}'",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

    def _register_admin_tabs(self, module: Module) -> None:
        self._admin_tabs.extend(module.admin_tabs)

    def _register_settings_fields(self, module: Module) -> None:
        self._settings_fields.extend(module.settings_fields)

    def _register_cli_commands(self, module: Module) -> None:
        self._cli_commands.extend(module.cli_commands)

    def _register_mcp_servers(self, module: Module) -> None:
        self._mcp_servers.extend(module.mcp_servers)

    def _register_trace_listeners(self, module: Module) -> None:
        self._trace_listeners.extend(module.trace_listeners)

    def _activate_token_counter(self) -> None:
        if self._token_counter is None:
            return
        from api.request_pipeline import set_module_token_counter

        set_module_token_counter(self._token_counter)

    def _activate_system_directives(self) -> None:
        if not self._system_directives:
            return
        from api.request_pipeline import set_module_system_directives

        set_module_system_directives(list(self._system_directives))

    def _activate_trace_listeners(self) -> None:
        if not self._trace_listeners:
            return
        from core.trace import add_trace_listeners

        add_trace_listeners(self._trace_listeners)

    def _publish_admin_tabs(self, app: FastAPI) -> None:
        # Stored on the app so /admin/api/modules/tabs can read it.
        existing = list(getattr(app.state, "admin_tabs", []))
        existing.extend(self._admin_tabs)
        app.state.admin_tabs = existing

    def _publish_cli_commands(self, app: FastAPI) -> None:
        existing = list(getattr(app.state, "cli_commands", []))
        existing.extend(self._cli_commands)
        app.state.cli_commands = existing

    def _publish_mcp_servers(self, app: FastAPI) -> None:
        existing = list(getattr(app.state, "mcp_servers", []))
        existing.extend(self._mcp_servers)
        app.state.mcp_servers = existing

    def _build_module_settings(self) -> None:
        if not self._settings_fields:
            return
        from config.module_settings import rebuild_module_settings

        rebuild_module_settings(self._settings_fields)

    def apply_middlewares(self, app: FastAPI) -> None:
        """Phase 2: register every stashed module middleware on the app.

        Must be called *after* the trace-correlation middleware has been
        registered so module middlewares wrap it (i.e. module auth runs
        *before* the trace middleware binds the request id to logs).
        """

        for middleware_class in self._middlewares:
            try:
                app.add_middleware(middleware_class)
            except Exception as exc:
                _log_error(
                    "Module middleware could not be applied",
                    exc,
                    verbose=_load_verbosity_pre(),
                )

    def admin_tabs(self) -> list[Any]:
        """Return the list of admin tab specs registered by all loaded modules."""

        return list(self._admin_tabs)

    def cli_commands(self) -> list[ModuleCliCommand]:
        """Return the list of CLI subcommands registered by all loaded modules."""

        return list(self._cli_commands)

    def mcp_servers(self) -> list[ModuleMcpServer]:
        """Return the list of MCP server backends registered by all loaded modules."""

        return list(self._mcp_servers)

    def settings_fields(self) -> list[ModuleSettingSpec]:
        """Return the list of declared module settings fields."""

        return list(self._settings_fields)

    async def run_startup(self, app: FastAPI, settings: Settings) -> None:
        """Run startup hooks for all loaded modules."""

        for module in self.modules:
            for hook in module.startup_hooks:
                try:
                    await hook(app, settings)
                except Exception as exc:
                    _log_error(
                        f"Module '{module.name}' startup hook failed",
                        exc,
                        verbose=_load_verbosity_pre(),
                    )

    async def run_shutdown(self, app: FastAPI, settings: Settings) -> None:
        """Run shutdown hooks for all loaded modules in reverse order."""

        for module in reversed(self.modules):
            for hook in module.shutdown_hooks:
                try:
                    await hook(app, settings)
                except Exception as exc:
                    _log_error(
                        f"Module '{module.name}' shutdown hook failed",
                        exc,
                        verbose=_load_verbosity_pre(),
                    )

    def reset(self) -> None:
        """Remove all module contributions from global state (tests only)."""

        from api.request_pipeline import (
            remove_message_intercepts,
            remove_reroute_strategies,
            reset_module_token_counter,
            set_module_system_directives,
        )
        from config.module_settings import clear_module_settings
        from config.provider_catalog import PROVIDER_CATALOG
        from config.provider_ids import SUPPORTED_PROVIDER_IDS
        from core.trace import remove_trace_listeners
        from messaging.platforms.factory import unregister_messaging_platforms
        from providers.registry import PROVIDER_FACTORIES

        for provider_id in self._provider_ids:
            PROVIDER_CATALOG.pop(provider_id, None)
            PROVIDER_FACTORIES.pop(provider_id, None)
            with contextlib.suppress(ValueError):
                SUPPORTED_PROVIDER_IDS.remove(provider_id)

        if self._message_intercepts:
            remove_message_intercepts(self._message_intercepts)

        if self._optimization_handlers:
            from api.optimization_handlers import OPTIMIZATION_HANDLERS

            for handler in self._optimization_handlers:
                with contextlib.suppress(ValueError):
                    OPTIMIZATION_HANDLERS.remove(handler)

        if self._reroute_strategies:
            remove_reroute_strategies(self._reroute_strategies)

        if self._system_directives:
            set_module_system_directives([])

        if self._token_counter is not None:
            reset_module_token_counter()
            self._token_counter = None

        if self._messaging_platforms:
            unregister_messaging_platforms(self._messaging_platforms)

        if self._trace_listeners:
            remove_trace_listeners(self._trace_listeners)

        clear_module_settings()

        self.modules.clear()
        self.failed.clear()
        self._provider_ids.clear()
        self._router_count = 0
        self._message_intercepts.clear()
        self._optimization_handlers.clear()
        self._reroute_strategies.clear()
        self._system_directives.clear()
        self._messaging_platforms.clear()
        self._admin_tabs.clear()
        self._settings_fields.clear()
        self._cli_commands.clear()
        self._mcp_servers.clear()
        self._trace_listeners.clear()
        self._middlewares.clear()


def list_module_dependencies() -> Iterable[type]:
    """Re-export hook so test-only imports of the loader's helpers stay local."""
    return ()


__all__ = [
    "ModuleManager",
]
