"""Tests for the Freebuff credentials reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.freebuff.credentials import (
    credentials_path,
    credentials_status,
    read_auth_tokens,
)


@pytest.fixture()
def tmp_credentials(tmp_path: Path):
    """Create a temporary credentials file."""
    creds_path = tmp_path / "credentials.json"
    return creds_path


# ---------------------------------------------------------------------------
# credentials_path tests
# ---------------------------------------------------------------------------


def test_credentials_path_default():
    path = credentials_path()
    assert path.name == "credentials.json"
    assert ".config" in str(path)
    assert "manicode" in str(path)


def test_credentials_path_override(tmp_path: Path):
    custom = tmp_path / "custom" / "creds.json"
    path = credentials_path(custom)
    assert path == custom


# ---------------------------------------------------------------------------
# read_auth_tokens tests
# ---------------------------------------------------------------------------


def test_read_auth_tokens_missing_file(tmp_path: Path):
    missing = tmp_path / "nonexistent.json"
    tokens = read_auth_tokens(missing)
    assert tokens == []


def test_read_auth_tokens_empty_file(tmp_credentials: Path):
    tmp_credentials.write_text("{}", encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert tokens == []


def test_read_auth_tokens_single_profile(tmp_credentials: Path):
    data = {
        "default": {
            "authToken": "fa82b5c1-e39d-4abc-bdef-1234567890ab",
            "other": "field",
        }
    }
    tmp_credentials.write_text(json.dumps(data), encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert tokens == ["fa82b5c1-e39d-4abc-bdef-1234567890ab"]


def test_read_auth_tokens_multiple_profiles(tmp_credentials: Path):
    data = {
        "default": {"authToken": "token-aaa"},
        "profile2": {"authToken": "token-bbb"},
        "profile3": {"authToken": "token-ccc"},
    }
    tmp_credentials.write_text(json.dumps(data), encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert len(tokens) == 3
    assert "token-aaa" in tokens
    assert "token-bbb" in tokens
    assert "token-ccc" in tokens


def test_read_auth_tokens_skips_empty_tokens(tmp_credentials: Path):
    data = {
        "default": {"authToken": "valid-token"},
        "empty": {"authToken": ""},
        "missing": {"noToken": "value"},
        "whitespace": {"authToken": "   "},
    }
    tmp_credentials.write_text(json.dumps(data), encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert tokens == ["valid-token"]


def test_read_auth_tokens_skips_non_dict_profiles(tmp_credentials: Path):
    data = {
        "default": {"authToken": "token-aaa"},
        "invalid": "not-a-dict",
        "number": 42,
    }
    tmp_credentials.write_text(json.dumps(data), encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert tokens == ["token-aaa"]


def test_read_auth_tokens_malformed_json(tmp_credentials: Path):
    tmp_credentials.write_text("not valid json{{", encoding="utf-8")
    tokens = read_auth_tokens(tmp_credentials)
    assert tokens == []


# ---------------------------------------------------------------------------
# credentials_status tests
# ---------------------------------------------------------------------------


def test_credentials_status_missing_file(tmp_path: Path):
    missing = tmp_path / "nonexistent.json"
    status = credentials_status(missing)
    assert status["found"] is False
    assert status["token_count"] == 0
    assert status["profiles"] == []


def test_credentials_status_valid_file(tmp_credentials: Path):
    data = {
        "default": {"authToken": "token-aaa"},
        "profile2": {"authToken": "token-bbb"},
    }
    tmp_credentials.write_text(json.dumps(data), encoding="utf-8")
    status = credentials_status(tmp_credentials)
    assert status["found"] is True
    assert status["token_count"] == 2
    assert "default" in status["profiles"]
    assert "profile2" in status["profiles"]


def test_credentials_status_malformed_json(tmp_credentials: Path):
    tmp_credentials.write_text("bad json", encoding="utf-8")
    status = credentials_status(tmp_credentials)
    assert status["found"] is False
