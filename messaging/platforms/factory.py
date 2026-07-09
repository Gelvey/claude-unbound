"""Messaging platform factory.

Creates the appropriate messaging platform adapter based on configuration.
To add a new platform (e.g. Discord, Slack):
1. Create a new class implementing MessagingPlatform in messaging/platforms/
2. Register it from a custom module via
   ``Module(...).messaging_platform(name, factory)``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from .base import MessagingPlatform


@dataclass(frozen=True, slots=True)
class MessagingPlatformOptions:
    """Typed wiring from :class:`~api.runtime.AppRuntime` into platform adapters."""

    telegram_bot_token: str | None = None
    allowed_telegram_user_id: str | None = None
    discord_bot_token: str | None = None
    allowed_discord_channels: str | None = None
    voice_note_enabled: bool = True
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    hf_token: str = ""
    nvidia_nim_api_key: str = ""
    messaging_rate_limit: int = 1
    messaging_rate_window: float = 1.0
    log_raw_messaging_content: bool = False
    log_api_error_tracebacks: bool = False


_PlatformFactory = Callable[[MessagingPlatformOptions], MessagingPlatform | None]

# Built-in platform factories.
_PLATFORM_FACTORIES: dict[str, _PlatformFactory] = {}


def _register_builtin_platforms() -> None:
    """Lazily import and register the built-in Telegram and Discord platforms."""

    if "none" in _PLATFORM_FACTORIES:
        return

    def _none_factory(_opts: MessagingPlatformOptions) -> None:
        logger.info("Messaging platform disabled by configuration")
        return None

    def _telegram_factory(opts: MessagingPlatformOptions) -> MessagingPlatform | None:
        bot_token = opts.telegram_bot_token
        if not bot_token:
            logger.info("No Telegram bot token configured, skipping platform setup")
            return None

        from .telegram import TelegramPlatform

        return TelegramPlatform(
            bot_token=bot_token,
            allowed_user_id=opts.allowed_telegram_user_id,
            voice_note_enabled=opts.voice_note_enabled,
            whisper_model=opts.whisper_model,
            whisper_device=opts.whisper_device,
            hf_token=opts.hf_token,
            nvidia_nim_api_key=opts.nvidia_nim_api_key,
            messaging_rate_limit=opts.messaging_rate_limit,
            messaging_rate_window=opts.messaging_rate_window,
            log_raw_messaging_content=opts.log_raw_messaging_content,
            log_api_error_tracebacks=opts.log_api_error_tracebacks,
        )

    def _discord_factory(opts: MessagingPlatformOptions) -> MessagingPlatform | None:
        bot_token = opts.discord_bot_token
        if not bot_token:
            logger.info("No Discord bot token configured, skipping platform setup")
            return None

        from .discord import DiscordPlatform

        return DiscordPlatform(
            bot_token=bot_token,
            allowed_channel_ids=opts.allowed_discord_channels,
            voice_note_enabled=opts.voice_note_enabled,
            whisper_model=opts.whisper_model,
            whisper_device=opts.whisper_device,
            hf_token=opts.hf_token,
            nvidia_nim_api_key=opts.nvidia_nim_api_key,
            messaging_rate_limit=opts.messaging_rate_limit,
            messaging_rate_window=opts.messaging_rate_window,
            log_raw_messaging_content=opts.log_raw_messaging_content,
            log_api_error_tracebacks=opts.log_api_error_tracebacks,
        )

    _PLATFORM_FACTORIES.update(
        {
            "none": _none_factory,
            "telegram": _telegram_factory,
            "discord": _discord_factory,
        }
    )


def register_messaging_platform(
    name: str,
    factory: _PlatformFactory,
) -> None:
    """Register a messaging platform factory (used by custom modules)."""

    if name in _PLATFORM_FACTORIES:
        raise ValueError(f"Messaging platform '{name}' is already registered")
    _PLATFORM_FACTORIES[name] = factory


def unregister_messaging_platforms(names: list[str]) -> None:
    """Remove platform factories (used by tests resetting module state)."""

    for name in names:
        _PLATFORM_FACTORIES.pop(name, None)


def create_messaging_platform(
    platform_type: str,
    options: MessagingPlatformOptions | None = None,
) -> MessagingPlatform | None:
    """Create a messaging platform instance based on type.

    Args:
        platform_type: Platform identifier (``telegram``, ``discord``, ``none``,
            or a value registered by a custom module).
        options: Token, allowlist, and voice / transcription settings.

    Returns:
        Configured :class:`MessagingPlatform` instance, or None if not configured.
    """

    _register_builtin_platforms()
    opts = options or MessagingPlatformOptions()
    factory = _PLATFORM_FACTORIES.get(platform_type)
    if factory is None:
        known = ", ".join(f"'{n}'" for n in _PLATFORM_FACTORIES)
        logger.warning(
            "Unknown messaging platform: '{}'. Supported: {}",
            platform_type,
            known,
        )
        return None

    return factory(opts)
