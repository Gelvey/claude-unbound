"""RAM-only OpenRouter forced-provider session overrides (per-process).

Stores a provider slug the admin UI pins at runtime so the gateway routes
every OpenRouter request to that provider. The value lives only in process
memory — it is **never** written to ``.env``, ``pyproject.toml``, or any
other file and is lost on fcc-server restart. That is intentional: it is a
temporary operational knob, not a persisted setting.

The request builder (:mod:`providers.open_router.request`) reads
:meth:`OpenRouterSessionOverrides.provider_options` and merges the result
into the ``provider.order`` / ``provider.allow_fallbacks`` fields of the
outgoing OpenRouter body. ``data_collection`` is left untouched here — it is
still resolved from the persisted OpenRouter policy settings so ZDR
enforcement is preserved.
"""

from __future__ import annotations

import threading
from typing import Any


class OpenRouterSessionOverrides:
    """Process-singleton holding the admin-pinned OpenRouter provider.

    A singleton is the right shape for a RAM-only, per-session knob: there is
    exactly one fcc-server process per host and the admin UI speaks to that
    process. Use :meth:`instance` to reach it; tests reset state with
    :meth:`clear` (or :meth:`reset`).
    """

    _instance: OpenRouterSessionOverrides | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._forced_provider: str | None = None
        self._allow_fallbacks: bool = False

    @classmethod
    def instance(cls) -> OpenRouterSessionOverrides:
        """Return the process-wide singleton, creating it on first use."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Drop the singleton so the next :meth:`instance` call starts fresh.

        Intended for tests that want a clean slate without leaking global
        state across cases. Production code should use :meth:`clear` /
        :meth:`set`.
        """
        cls._instance = None

    def set(self, provider: str | None, *, allow_fallbacks: bool = False) -> None:
        """Pin the forced provider slug, or clear it when ``provider`` is empty.

        ``allow_fallbacks`` defaults to ``False`` so "forcing" really forces:
        OpenRouter will not route the request to any other provider if the
        pinned one is unavailable. Operators who want graceful fallback can
        opt in explicitly via the admin UI.
        """
        slug = provider.strip() if isinstance(provider, str) else provider
        if not slug:
            slug = None
        with self._lock:
            self._forced_provider = slug
            self._allow_fallbacks = bool(allow_fallbacks)

    def clear(self) -> None:
        """Remove the forced provider so routing returns to OpenRouter default."""
        with self._lock:
            self._forced_provider = None
            self._allow_fallbacks = False

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-ready copy of the current state for the admin UI."""
        with self._lock:
            if not self._forced_provider:
                return {"forced_provider": None, "allow_fallbacks": False}
            return {
                "forced_provider": self._forced_provider,
                "allow_fallbacks": self._allow_fallbacks,
            }

    def provider_options(self) -> dict[str, Any] | None:
        """Return the ``provider`` routing fragment to deep-merge, or ``None``.

        Returns ``None`` when no provider is pinned so the request builder
        skips the merge entirely and the outgoing body is unchanged. When a
        provider is pinned, returns ``{"order": [<slug>], "allow_fallbacks":
        bool}`` — the OpenRouter-canonical way to force a single backend.
        """
        with self._lock:
            if not self._forced_provider:
                return None
            return {
                "order": [self._forced_provider],
                "allow_fallbacks": self._allow_fallbacks,
            }
