"""Dataclass contract and type aliases for custom modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from api.models.anthropic import MessagesRequest
    from api.models.responses import MessagesResponse
    from api.request_pipeline import MessageIntercept
    from config.provider_catalog import ProviderDescriptor
    from config.settings import Settings
    from messaging.platforms.base import MessagingPlatform
    from providers.registry import ProviderFactory

    OptimizationHandler = Callable[[MessagesRequest, Settings], MessagesResponse | None]


@dataclass(frozen=False, slots=True)
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
    message_intercepts: list[MessageIntercept] = field(default_factory=list)
    optimization_handlers: list[OptimizationHandler] = field(default_factory=list)
    messaging_platform_factories: dict[str, Callable[..., MessagingPlatform]] = field(
        default_factory=dict
    )
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

    def intercept(self, fn: MessageIntercept) -> Module:
        """Register a message intercept."""

        self.message_intercepts.append(fn)
        return self

    def optimizer(self, fn: OptimizationHandler) -> Module:
        """Register an optimization handler."""

        self.optimization_handlers.append(fn)
        return self

    def messaging_platform(
        self,
        name: str,
        factory: Callable[..., MessagingPlatform],
    ) -> Module:
        """Register a messaging platform factory."""

        self.messaging_platform_factories[name] = factory
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
