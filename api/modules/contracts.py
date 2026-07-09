"""Dataclass contract and type aliases for custom modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from api.models.anthropic import MessagesRequest
    from api.models.responses import MessagesResponse
    from api.request_pipeline import (
        MessageIntercept,
        RoutedMessagesRequest,
        TokenCounter,
    )
    from config.provider_catalog import ProviderDescriptor
    from config.settings import Settings
    from messaging.platforms.base import MessagingPlatform
    from providers.registry import ProviderFactory

    OptimizationHandler = Callable[[MessagesRequest, Settings], MessagesResponse | None]
    RerouteStrategy = Callable[
        [RoutedMessagesRequest, Settings], RoutedMessagesRequest | None
    ]
    TraceListener = Callable[[str, str, str, dict[str, Any]], None]
    CliCommandHandler = Callable[[list[str]], int]


@dataclass(frozen=True, slots=True)
class AdminTabSpec:
    """A custom tab the module contributes to the admin UI."""

    id: str
    label: str
    title: str
    html: str
    mount_js: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleSettingSpec:
    """One Settings field a module declares."""

    alias: str
    type: type
    default: Any = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class ModuleCliCommand:
    """A CLI subcommand registered by a module."""

    name: str
    help: str
    handler: CliCommandHandler


@dataclass(frozen=True, slots=True)
class ModuleMcpServer:
    """An MCP server backend a module wants in mcp_config.json."""

    name: str
    backend: (
        Any  # McpBackend; imported lazily to avoid a Pydantic cycle at import time.
    )


@dataclass(frozen=False, slots=False)
class Module:
    """Contract exposed by a custom module.

    A module sets ``FCC_MODULE = Module(...)`` or returns one from
    ``setup_module(app, settings)``. Optional fields default to empty
    containers when omitted.
    """

    name: str
    version: str = "0.0.0"
    provider_descriptors: dict[str, ProviderDescriptor] = field(default_factory=dict)
    provider_factories: dict[str, ProviderFactory] = field(default_factory=dict)
    routers: list[APIRouter] = field(default_factory=list)
    middlewares: list[type] = field(default_factory=list)
    message_intercepts: list[MessageIntercept] = field(default_factory=list)
    optimization_handlers: list[OptimizationHandler] = field(default_factory=list)
    reroute_strategies: list[RerouteStrategy] = field(default_factory=list)
    system_directives: list[str] = field(default_factory=list)
    token_counter_override: TokenCounter | None = field(default=None, repr=False)
    messaging_platform_factories: dict[str, Callable[..., MessagingPlatform]] = field(
        default_factory=dict
    )
    admin_tabs: list[AdminTabSpec] = field(default_factory=list)
    settings_fields: list[ModuleSettingSpec] = field(default_factory=list)
    cli_commands: list[ModuleCliCommand] = field(default_factory=list)
    mcp_servers: list[ModuleMcpServer] = field(default_factory=list)
    trace_listeners: list[TraceListener] = field(default_factory=list)
    startup_hooks: list[Callable[[FastAPI, Settings], Awaitable[None]]] = field(
        default_factory=list
    )
    shutdown_hooks: list[Callable[[FastAPI, Settings], Awaitable[None]]] = field(
        default_factory=list
    )

    def provider(
        self,
        provider_id: str,
        descriptor: ProviderDescriptor,
        factory: ProviderFactory,
    ) -> Module:
        """Register a custom provider."""

        self.provider_descriptors[provider_id] = descriptor
        self.provider_factories[provider_id] = factory
        return self

    def router(self, router: APIRouter) -> Module:
        """Register a FastAPI router."""

        self.routers.append(router)
        return self

    def middleware(self, middleware_class: type) -> Module:
        """Register a Starlette/FastAPI middleware class (added outside the trace middleware)."""

        self.middlewares.append(middleware_class)
        return self

    def intercept(self, fn: MessageIntercept) -> Module:
        """Register a message intercept."""

        self.message_intercepts.append(fn)
        return self

    def optimizer(self, fn: OptimizationHandler) -> Module:
        """Register an optimization handler."""

        self.optimization_handlers.append(fn)
        return self

    def reroute(self, fn: RerouteStrategy) -> Module:
        """Register a reroute strategy that may rewrite the routed request."""

        self.reroute_strategies.append(fn)
        return self

    def system_directive(self, text: str) -> Module:
        """Register a constant system-prompt directive appended to every MessagesRequest."""

        self.system_directives.append(text)
        return self

    def token_counter(self, fn: TokenCounter) -> Module:
        """Override the request token counter (last-registered wins)."""

        self.token_counter_override = fn
        return self

    def messaging_platform(
        self,
        name: str,
        factory: Callable[..., MessagingPlatform],
    ) -> Module:
        """Register a messaging platform factory."""

        self.messaging_platform_factories[name] = factory
        return self

    def admin_tab(
        self,
        *,
        id: str,
        label: str,
        title: str,
        html: str,
        mount_js: str | None = None,
    ) -> Module:
        """Register a custom tab in the admin UI."""

        self.admin_tabs.append(
            AdminTabSpec(id=id, label=label, title=title, html=html, mount_js=mount_js)
        )
        return self

    def setting(
        self,
        *,
        alias: str,
        type: type,
        default: Any = None,
        description: str = "",
    ) -> Module:
        """Declare a Settings field that this module reads."""

        self.settings_fields.append(
            ModuleSettingSpec(
                alias=alias, type=type, default=default, description=description
            )
        )
        return self

    def cli_command(
        self,
        *,
        name: str,
        help: str,
        handler: CliCommandHandler,
    ) -> Module:
        """Register a CLI subcommand invoked as ``fcc <name> [args...]``."""

        self.cli_commands.append(
            ModuleCliCommand(name=name, help=help, handler=handler)
        )
        return self

    def mcp_server(self, *, name: str, backend: Any) -> Module:
        """Register an MCP server backend (added to mcp_config.json on next write)."""

        self.mcp_servers.append(ModuleMcpServer(name=name, backend=backend))
        return self

    def trace_listener(self, fn: TraceListener) -> Module:
        """Register a function called for every trace event."""

        self.trace_listeners.append(fn)
        return self

    def on_startup(
        self,
        fn: Callable[[FastAPI, Settings], Awaitable[None]],
    ) -> Module:
        """Register a startup hook."""

        self.startup_hooks.append(fn)
        return self

    def on_shutdown(
        self,
        fn: Callable[[FastAPI, Settings], Awaitable[None]],
    ) -> Module:
        """Register a shutdown hook."""

        self.shutdown_hooks.append(fn)
        return self
