"""Tests for module lifecycle hook integration in AppRuntime."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from api.runtime import AppRuntime


@pytest.mark.asyncio
async def test_module_shutdown_hooks_run_before_core_services_stop():
    """Shutdown hooks must execute while provider registry is still alive."""

    app = MagicMock()
    settings = MagicMock()
    type(settings).log_api_error_tracebacks = PropertyMock(return_value=False)

    runtime = AppRuntime(app=app, settings=settings)

    provider_cleanup_started = False
    shutdown_hook_executed_before_cleanup = False

    async def fake_shutdown_hook(_app, _settings) -> None:
        nonlocal shutdown_hook_executed_before_cleanup
        shutdown_hook_executed_before_cleanup = not provider_cleanup_started

    async def fake_provider_cleanup() -> None:
        nonlocal provider_cleanup_started
        provider_cleanup_started = True

    module_manager = MagicMock()
    module_manager.run_shutdown = AsyncMock(side_effect=fake_shutdown_hook)
    app.state.modules = module_manager

    registry = MagicMock()
    registry.cleanup = AsyncMock(side_effect=fake_provider_cleanup)
    runtime._provider_registry = registry

    await runtime.shutdown()

    module_manager.run_shutdown.assert_awaited_once()
    registry.cleanup.assert_awaited_once()
    assert shutdown_hook_executed_before_cleanup
