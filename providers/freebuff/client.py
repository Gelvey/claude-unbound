"""Freebuff2API provider (OpenAI-compatible chat completions via managed proxy).

Freebuff2API is a Go binary that acts as an OpenAI-compatible proxy to
codebuff.com.  It manages free agent sessions with token rotation and
dynamically fetches available models from codebuff's source.

When managed by :class:`~providers.freebuff.manager.FreebuffManager`, the
base URL is set dynamically to ``http://127.0.0.1:<port>``.
"""

from __future__ import annotations

import contextlib
from typing import Any

import httpx
from loguru import logger
from openai import APIConnectionError, AsyncOpenAI

from providers.base import (
    ProviderConfig,
    provider_http_limits,
    provider_http_timeout,
)
from providers.defaults import FREEBUFF_DEFAULT_BASE
from providers.transports.openai_chat import OpenAIChatTransport

from .binary_manager import check_container_running
from .config_generator import read_config_port
from .request import build_request_body


def normalize_freebuff_base_url(raw_url: str) -> str:
    """Return a base URL ending in ``/v1`` for the OpenAI SDK."""
    url = raw_url.strip().rstrip("/")
    if not url:
        return url
    if url.endswith("/v1"):
        return url
    return f"{url}/v1"


class FreebuffProvider(OpenAIChatTransport):
    """Freebuff2API proxy at ``http://127.0.0.1:<port>/v1``."""

    def __init__(self, config: ProviderConfig):
        base_url = normalize_freebuff_base_url(config.base_url or FREEBUFF_DEFAULT_BASE)
        logger.info(
            "FREEBUFF_PROVIDER: init config_base_url={} normalized_base_url={}",
            config.base_url,
            base_url,
        )

        super().__init__(
            config,
            provider_name="FREEBUFF",
            base_url=base_url,
            api_key=config.api_key or "freebuff",
        )

    async def _detect_container_url(self) -> str | None:
        """Detect the running proxy URL from Docker or the manager config file."""
        logger.debug("FREEBUFF_PROVIDER: detecting container URL")
        try:
            status = await check_container_running()
            logger.debug(
                "FREEBUFF_PROVIDER: container_status running={} host_port={} status={} error={}",
                status.get("running"),
                status.get("host_port"),
                status.get("status"),
                status.get("error"),
            )
            if status["running"] and status.get("host_port"):
                url = normalize_freebuff_base_url(
                    f"http://127.0.0.1:{status['host_port']}"
                )
                logger.info("FREEBUFF_PROVIDER: detected container at {}", url)
                return url
        except Exception as exc:
            logger.warning("FREEBUFF_PROVIDER: container detection failed: {}", exc)

        # Fallback to the config file written by FreebuffManager (covers source
        # builds and Docker when the container name is not inspectable).
        try:
            port = read_config_port()
            logger.debug("FREEBUFF_PROVIDER: config_file port={}", port)
            if port:
                url = normalize_freebuff_base_url(f"http://127.0.0.1:{port}")
                logger.info("FREEBUFF_PROVIDER: detected config port at {}", url)
                return url
        except Exception as exc:
            logger.warning("FREEBUFF_PROVIDER: config port detection failed: {}", exc)

        logger.info(
            "FREEBUFF_PROVIDER: no container URL detected (configured_base_url={})",
            self._base_url,
        )
        return None

    async def list_model_ids(self) -> frozenset[str]:
        """Return model ids, auto-detecting the container port if needed."""
        detected = await self._detect_container_url()
        urls_to_try: list[str] = []
        # Prefer the auto-detected URL if it differs from the configured one.
        if detected and detected != self._base_url:
            urls_to_try.append(f"{detected}/models")
        urls_to_try.append(f"{self._base_url}/models")

        async with httpx.AsyncClient(timeout=10) as client:
            for url in urls_to_try:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    ids = [
                        m["id"]
                        for m in data.get("data", [])
                        if isinstance(m, dict) and m.get("id")
                    ]
                    return frozenset(ids)
                except Exception as exc:
                    logger.warning(
                        "FREEBUFF_PROVIDER: model list failed at {}: {}", url, exc
                    )

        # All URLs failed — return empty set.
        return frozenset()

    async def _rebuild_openai_client(self) -> None:
        """Rebuild the OpenAI client after :attr:`_base_url` changed."""
        old_client = self._client
        self._http_client = httpx.AsyncClient(
            proxy=self._config.proxy or None,
            timeout=provider_http_timeout(self._config),
            limits=provider_http_limits(self._config),
            http2=self._config.http2,
        )
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=0,
            timeout=provider_http_timeout(self._config),
            http_client=self._http_client,
        )
        if old_client is not None:
            with contextlib.suppress(Exception):
                await old_client.close()

    async def _start_stream(self, body: dict[str, Any]) -> Any:
        """Open the chat stream, refreshing the client if the proxy moved.

        The auto-detected URL is tried first; if it fails with a connection
        error we fall back to the configured URL so stale detection (e.g. an
        old Docker port binding) doesn't break the request.
        """
        detected = await self._detect_container_url()
        urls_to_try: list[str] = [self._base_url]
        if detected and detected != self._base_url:
            urls_to_try.insert(0, detected)
        logger.info(
            "FREEBUFF_PROVIDER: stream start configured={} detected={} urls_to_try={}",
            self._base_url,
            detected,
            urls_to_try,
        )

        original_url = self._base_url
        last_error: Exception | None = None
        for idx, url in enumerate(urls_to_try):
            if url != self._base_url:
                logger.info(
                    "FREEBUFF_PROVIDER: switching base_url from {} to {}",
                    self._base_url,
                    url,
                )
                self._base_url = url
                await self._rebuild_openai_client()

            try:
                result = await super()._start_stream(body)
                logger.info(
                    "FREEBUFF_PROVIDER: stream succeeded url={} attempts={}",
                    url,
                    idx + 1,
                )
                return result
            except Exception as exc:
                last_error = exc
                is_connection_error = isinstance(
                    exc,
                    (
                        httpx.ConnectError,
                        httpx.ConnectTimeout,
                        APIConnectionError,
                    ),
                )
                logger.warning(
                    "FREEBUFF_PROVIDER: stream failed url={} error_type={} "
                    "connection_error={} error={}",
                    url,
                    type(exc).__name__,
                    is_connection_error,
                    exc,
                )
                if not is_connection_error or idx == len(urls_to_try) - 1:
                    raise

                # Reset to the original configured URL before the fallback.
                if self._base_url != original_url:
                    logger.info(
                        "FREEBUFF_PROVIDER: falling back to configured base_url={}",
                        original_url,
                    )
                    self._base_url = original_url
                    await self._rebuild_openai_client()

        # Defensive: should only reach here if urls_to_try was empty.
        if last_error is not None:
            raise last_error
        return await super()._start_stream(body)

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
        )
