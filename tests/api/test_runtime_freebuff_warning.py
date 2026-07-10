"""Tests for the Freebuff session-hygiene startup warning."""

import logging

from api.runtime import warn_if_freebuff_session_hygiene
from config.settings import Settings


def test_warns_when_freebuff_enabled(caplog) -> None:
    settings = Settings()
    settings.freebuff_enabled = True

    with caplog.at_level(logging.WARNING):
        warn_if_freebuff_session_hygiene(settings)

    blob = " | ".join(r.getMessage() for r in caplog.records)
    assert "FREEBUFF enabled" in blob
    assert "suspend" in blob.lower()


def test_silent_when_freebuff_disabled(caplog) -> None:
    settings = Settings()
    settings.freebuff_enabled = False

    with caplog.at_level(logging.WARNING):
        warn_if_freebuff_session_hygiene(settings)

    blob = " | ".join(r.getMessage() for r in caplog.records)
    assert "FREEBUFF" not in blob
