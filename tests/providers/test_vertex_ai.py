"""Tests for Google Vertex AI (OpenAI-compatible) provider."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.base import ProviderConfig
from providers.exceptions import AuthenticationError, ModelListResponseError
from providers.vertex_ai.auth import GoogleAccessTokenProvider, VertexAIAuth
from providers.vertex_ai.client import VertexAIProvider
from providers.vertex_ai.endpoint import (
    vertex_openai_base_url,
    vertex_publisher_models_url,
    vertex_service_endpoint,
)
from providers.vertex_ai.models import extract_vertex_model_page
from providers.vertex_ai.request import build_request_body


class MockMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class MockRequest:
    def __init__(self, **kwargs):
        self.model = "google/gemini-2.5-flash"
        self.messages = [MockMessage("user", "Hello")]
        self.max_tokens = 100
        self.temperature = 0.5
        self.top_p = 0.9
        self.system = "System prompt"
        self.stop_sequences = None
        self.tools = []
        self.thinking = MagicMock()
        self.thinking.enabled = True
        for key, value in kwargs.items():
            setattr(self, key, value)


def _vertex_config(**overrides):
    api_key = str(overrides.get("api_key", "vertex-ai"))
    base_url = str(
        overrides.get("base_url", vertex_openai_base_url("test-project", "global"))
    )
    rate_limit = int(overrides.get("rate_limit", 10))
    rate_window = int(overrides.get("rate_window", 60))
    enable_thinking = bool(overrides.get("enable_thinking", True))
    return ProviderConfig(
        api_key=api_key,
        base_url=base_url,
        rate_limit=rate_limit,
        rate_window=rate_window,
        enable_thinking=enable_thinking,
    )


@pytest.fixture(autouse=True)
def mock_rate_limiter():
    @asynccontextmanager
    async def _slot():
        yield

    with patch("providers.transports.openai_chat.transport.GlobalRateLimiter") as mock:
        instance = mock.get_scoped_instance.return_value

        async def _passthrough(fn, *args, **kwargs):
            return await fn(*args, **kwargs)

        instance.execute_with_retry = AsyncMock(side_effect=_passthrough)
        instance.concurrency_slot.side_effect = _slot
        yield instance


# --- Endpoint construction ---


def test_endpoint_global():
    url = vertex_openai_base_url("my-project", "global")
    assert url == (
        "https://aiplatform.googleapis.com/v1/projects/my-project/locations/"
        "global/endpoints/openapi"
    )


def test_endpoint_regional():
    url = vertex_openai_base_url("my-project", "us-central1")
    assert url == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/"
        "locations/us-central1/endpoints/openapi"
    )


def test_service_endpoint_global():
    assert vertex_service_endpoint("global") == "https://aiplatform.googleapis.com"


def test_service_endpoint_regional():
    assert (
        vertex_service_endpoint("us-central1")
        == "https://us-central1-aiplatform.googleapis.com"
    )


def test_publisher_models_url():
    url = vertex_publisher_models_url("us-central1")
    assert "us-central1-aiplatform.googleapis.com" in url
    assert "/v1beta1/publishers/google/models" in url


def test_endpoint_empty_project_raises():
    with pytest.raises(ValueError, match="VERTEX_AI_PROJECT_ID"):
        vertex_openai_base_url("", "global")


def test_endpoint_empty_location_raises():
    with pytest.raises(ValueError, match="VERTEX_AI_LOCATION"):
        vertex_openai_base_url("proj", "")


def test_endpoint_invalid_location_raises():
    with pytest.raises(ValueError, match="lowercase Google Cloud region"):
        vertex_openai_base_url("proj", "Invalid Region!")


# --- Request body ---


def test_build_request_body_thinking_enabled():
    body = build_request_body(MockRequest(), thinking_enabled=True)
    assert body["model"] == "google/gemini-2.5-flash"
    assert "reasoning_effort" not in body
    eb = body.get("extra_body")
    assert isinstance(eb, dict)
    literal_extra_body = eb.get("extra_body")
    assert isinstance(literal_extra_body, dict)
    google = literal_extra_body.get("google")
    assert isinstance(google, dict)
    tc = google.get("thinking_config")
    assert isinstance(tc, dict)
    assert tc.get("include_thoughts") is True


def test_build_request_body_thinking_disabled():
    body = build_request_body(MockRequest(), thinking_enabled=False)
    assert body["reasoning_effort"] == "none"
    assert "extra_body" not in body


def test_build_request_body_preserves_caller_extra_body():
    req = MockRequest(extra_body={"metadata": {"user": "u1"}})
    body = build_request_body(req, thinking_enabled=True)
    eb = body.get("extra_body")
    assert isinstance(eb, dict)
    assert eb.get("metadata") == {"user": "u1"}


def test_build_request_body_merges_caller_nested_google():
    req = MockRequest(
        extra_body={
            "extra_body": {
                "google": {
                    "thinking_config": {"budget_tokens": 128},
                    "cached_content": "cachedContents/example",
                }
            },
        }
    )
    body = build_request_body(req, thinking_enabled=True)
    eb = body.get("extra_body")
    assert isinstance(eb, dict)
    literal_extra_body = eb.get("extra_body")
    assert isinstance(literal_extra_body, dict)
    google = literal_extra_body.get("google")
    assert isinstance(google, dict)
    assert google.get("cached_content") == "cachedContents/example"
    tc = google.get("thinking_config")
    assert isinstance(tc, dict)
    assert tc.get("budget_tokens") == 128
    assert tc.get("include_thoughts") is True


def test_build_request_body_preserves_tool_call_extra_content():
    req = MockRequest(
        system=None,
        model="google/gemini-2.5-flash",
        messages=[
            MockMessage("user", "Find files"),
            MockMessage(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "function-call-1",
                        "name": "Glob",
                        "input": {"pattern": "*.py"},
                        "extra_content": {
                            "google": {"thought_signature": "sig-from-client"}
                        },
                    }
                ],
            ),
            MockMessage(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "function-call-1",
                        "content": "[]",
                    }
                ],
            ),
        ],
    )
    body = build_request_body(req, thinking_enabled=True)
    tool_call = body["messages"][1]["tool_calls"][0]
    assert tool_call["extra_content"] == {
        "google": {"thought_signature": "sig-from-client"}
    }


def test_build_request_body_replays_cached_tool_call_signature():
    """A streamed signature recorded earlier is replayed on the next turn."""
    req = MockRequest(
        system=None,
        model="google/gemini-2.5-flash",
        messages=[
            MockMessage("user", "Find files"),
            MockMessage(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "function-call-1",
                        "name": "Glob",
                        "input": {"pattern": "*.py"},
                    }
                ],
            ),
            MockMessage(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "function-call-1",
                        "content": "[]",
                    }
                ],
            ),
        ],
    )
    cache = {"function-call-1": {"google": {"thought_signature": "sig-from-cache"}}}
    body = build_request_body(
        req, thinking_enabled=True, tool_call_extra_content_by_id=cache
    )
    tool_call = body["messages"][1]["tool_calls"][0]
    assert tool_call["extra_content"] == {
        "google": {"thought_signature": "sig-from-cache"}
    }


def test_build_request_body_adds_gemini3_current_turn_fallback_signature():
    """Gemini 3 assistant tool-calls without a signature get the skip sentinel."""
    req = MockRequest(
        system=None,
        model="google/gemini-3-pro",
        messages=[
            MockMessage("user", "Find files"),
            MockMessage(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "function-call-1",
                        "name": "Glob",
                        "input": {"pattern": "*.py"},
                    },
                    {
                        "type": "tool_use",
                        "id": "function-call-2",
                        "name": "Read",
                        "input": {"file_path": "a.py"},
                    },
                ],
            ),
            MockMessage(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "function-call-1",
                        "content": "[]",
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "function-call-2",
                        "content": "contents",
                    },
                ],
            ),
        ],
    )
    body = build_request_body(req, thinking_enabled=True)
    tool_calls = body["messages"][1]["tool_calls"]
    from providers.transports.openai_chat.google_signatures import (
        SKIP_THOUGHT_SIGNATURE_VALIDATOR,
    )

    assert tool_calls[0]["extra_content"] == {
        "google": {"thought_signature": SKIP_THOUGHT_SIGNATURE_VALIDATOR}
    }
    assert "extra_content" not in tool_calls[1]


def test_build_request_body_no_fallback_for_non_gemini3():
    """Gemini 2.5 does not receive the skip sentinel on missing signatures."""
    req = MockRequest(
        system=None,
        model="google/gemini-2.5-flash",
        messages=[
            MockMessage("user", "Find files"),
            MockMessage(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "function-call-1",
                        "name": "Glob",
                        "input": {"pattern": "*.py"},
                    }
                ],
            ),
            MockMessage(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "function-call-1",
                        "content": "[]",
                    }
                ],
            ),
        ],
    )
    body = build_request_body(req, thinking_enabled=True)
    tool_call = body["messages"][1]["tool_calls"][0]
    assert "extra_content" not in tool_call


@pytest.mark.asyncio
async def test_provider_records_streamed_tool_call_extra_content():
    """The provider overrides the recorder so streamed signatures are cached."""
    with (
        patch("providers.transports.openai_chat.transport.AsyncOpenAI"),
        patch("httpx.AsyncClient"),
    ):
        provider = VertexAIProvider(
            _vertex_config(),
            project_id="test-project",
            location="global",
        )
    provider._record_tool_call_extra_content(
        "function-call-1", {"google": {"thought_signature": "sig-stream"}}
    )
    assert provider._tool_call_extra_content_by_id == {
        "function-call-1": {"google": {"thought_signature": "sig-stream"}}
    }


# --- Model listing ---


def test_extract_vertex_model_page_basic():
    payload = {
        "publisherModels": [
            {"name": "publishers/google/models/gemini-2.5-flash"},
            {"name": "publishers/google/models/gemini-2.5-flash-lite"},
        ]
    }
    ids, next_token = extract_vertex_model_page(payload)
    assert ids == frozenset({"google/gemini-2.5-flash", "google/gemini-2.5-flash-lite"})
    assert next_token is None


def test_extract_vertex_model_page_with_pagination():
    payload = {
        "publisherModels": [
            {"name": "publishers/google/models/gemini-2.5-flash"},
        ],
        "nextPageToken": "token-abc",
    }
    ids, next_token = extract_vertex_model_page(payload)
    assert "google/gemini-2.5-flash" in ids
    assert next_token == "token-abc"


def test_extract_vertex_model_page_malformed_not_object():
    with pytest.raises(ModelListResponseError, match="expected an object"):
        extract_vertex_model_page("not a dict")


def test_extract_vertex_model_page_malformed_missing_array():
    with pytest.raises(
        ModelListResponseError, match="expected top-level publisherModels"
    ):
        extract_vertex_model_page({"wrongKey": []})


def test_extract_vertex_model_page_malformed_bad_name():
    with pytest.raises(ModelListResponseError, match="expected publisher model"):
        extract_vertex_model_page({"publisherModels": [{"name": "bad/format"}]})


# --- Auth ---


@pytest.mark.asyncio
async def test_token_provider_returns_token():
    fake_credentials = MagicMock()
    fake_credentials.valid = True
    fake_credentials.token = "ya29.test-token"

    loader = MagicMock(return_value=(fake_credentials, "test-project"))
    provider = GoogleAccessTokenProvider(credentials_loader=loader)
    token = await provider.get_token()
    assert token == "ya29.test-token"
    loader.assert_called_once()


@pytest.mark.asyncio
async def test_token_provider_refreshes_expired_token():
    fake_credentials = MagicMock()
    fake_credentials.valid = False
    fake_credentials.token = None

    def refresh_side_effect(*args, **kwargs):
        fake_credentials.valid = True
        fake_credentials.token = "ya29.refreshed"

    fake_credentials.refresh = MagicMock(side_effect=refresh_side_effect)

    loader = MagicMock(return_value=(fake_credentials, "test-project"))
    provider = GoogleAccessTokenProvider(credentials_loader=loader)
    token = await provider.get_token()
    assert token == "ya29.refreshed"
    fake_credentials.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_token_provider_raises_on_missing_adc():
    from google.auth.exceptions import DefaultCredentialsError

    loader = MagicMock(side_effect=DefaultCredentialsError("no creds"))
    provider = GoogleAccessTokenProvider(credentials_loader=loader)
    with pytest.raises(
        AuthenticationError, match="Application Default Credentials were not found"
    ):
        await provider.get_token()


@pytest.mark.asyncio
async def test_vertex_auth_flow_sets_headers():
    token_provider = AsyncMock()
    token_provider.get_token = AsyncMock(return_value="ya29.test-token")

    auth = VertexAIAuth(token_provider, "my-project")
    request = MagicMock()
    request.headers = {}

    async for _ in auth.async_auth_flow(request):
        pass

    assert request.headers["Authorization"] == "Bearer ya29.test-token"
    assert request.headers["x-goog-user-project"] == "my-project"


# --- Provider construction ---


def test_provider_init():
    with (
        patch("providers.transports.openai_chat.transport.AsyncOpenAI"),
        patch("httpx.AsyncClient"),
    ):
        provider = VertexAIProvider(
            _vertex_config(),
            project_id="test-project",
            location="global",
        )
    assert provider._provider_name == "VERTEX_AI"
    assert provider._project_id == "test-project"
    assert provider._location == "global"
    assert "aiplatform.googleapis.com" in provider._base_url
    assert "/v1/projects/test-project/" in provider._base_url
    assert "/locations/global/endpoints/openapi" in provider._base_url


def test_provider_init_regional():
    config = ProviderConfig(
        api_key="vertex-ai",
        base_url=vertex_openai_base_url("proj-123", "us-central1"),
    )
    with (
        patch("providers.transports.openai_chat.transport.AsyncOpenAI"),
        patch("httpx.AsyncClient"),
    ):
        provider = VertexAIProvider(
            config, project_id="proj-123", location="us-central1"
        )
    assert "us-central1-aiplatform.googleapis.com" in provider._base_url


def test_provider_build_request_body():
    with (
        patch("providers.transports.openai_chat.transport.AsyncOpenAI"),
        patch("httpx.AsyncClient"),
    ):
        provider = VertexAIProvider(
            _vertex_config(),
            project_id="test-project",
            location="global",
        )
    body = provider._build_request_body(MockRequest())
    assert body["model"] == "google/gemini-2.5-flash"
    assert "reasoning_effort" not in body


@pytest.mark.asyncio
async def test_provider_cleanup():
    with (
        patch("providers.transports.openai_chat.transport.AsyncOpenAI"),
        patch("httpx.AsyncClient"),
    ):
        provider = VertexAIProvider(
            _vertex_config(),
            project_id="test-project",
            location="global",
        )
    provider._client = AsyncMock()
    provider._model_list_client = AsyncMock()
    await provider.cleanup()
    provider._client.close.assert_called_once()
    provider._model_list_client.aclose.assert_called_once()
