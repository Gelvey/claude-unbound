"""Lazy tiktoken encoder: no BPE load at import time, cached on first use."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from core.anthropic import sse, tokens


@pytest.fixture()
def _reset_encoder():
    original = tokens._encoder
    tokens._encoder = None
    yield
    tokens._encoder = original


class TestGetEncoder:
    def test_loads_once_and_caches(self, _reset_encoder: None) -> None:
        with patch(
            "core.anthropic.tokens.tiktoken.get_encoding",
            wraps=tokens.tiktoken.get_encoding,
        ) as spy:
            first = tokens.get_encoder()
            second = tokens.get_encoder()
        assert first is second
        assert spy.call_count == 1

    def test_encoder_counts_tokens(self, _reset_encoder: None) -> None:
        assert len(tokens.get_encoder().encode("hello world")) > 0


class TestImportTimeLaziness:
    def test_import_does_not_initialize_encoder(self) -> None:
        """A fresh interpreter importing tokens must not load the encoder."""
        code = (
            "import core.anthropic.tokens as t; "
            "import core.anthropic.sse; "
            "raise SystemExit(0 if t._encoder is None else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert result.returncode == 0, result.stderr


class TestSseEncoderFallback:
    def test_encoder_or_none_returns_encoder(self) -> None:
        assert sse._encoder_or_none() is not None

    def test_encoder_or_none_swallows_load_failure(self) -> None:
        with patch(
            "core.anthropic.tokens.get_encoder",
            side_effect=RuntimeError("offline"),
        ):
            assert sse._encoder_or_none() is None
