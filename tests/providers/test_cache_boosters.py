"""Session-affinity keys and prompt_cache_key cache hit-rate boosters."""

from __future__ import annotations

from typing import Any

from api.models.anthropic import MessagesRequest
from core.anthropic.session_key import stable_session_key
from providers.cloudflare_ai.request import SESSION_AFFINITY_HEADER, build_request_body


def _request(**overrides: Any) -> MessagesRequest:
    payload: dict[str, Any] = {
        "model": "@cf/test/model",
        "max_tokens": 100,
        "system": "You are helpful.",
        "messages": [{"role": "user", "content": "hello"}],
    }
    payload.update(overrides)
    return MessagesRequest.model_validate(payload)


class TestStableSessionKey:
    def test_prefers_metadata_user_id(self) -> None:
        a = stable_session_key(_request(metadata={"user_id": "user-abc"}))
        b = stable_session_key(
            _request(
                metadata={"user_id": "user-abc"},
                messages=[{"role": "user", "content": "different text"}],
            )
        )
        assert a is not None
        assert a == b  # keyed by user_id, not message content

    def test_falls_back_to_system_plus_first_user_message(self) -> None:
        a = stable_session_key(_request())
        later_turn = _request(
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
                {"role": "user", "content": "next question"},
            ]
        )
        assert a is not None
        assert stable_session_key(later_turn) == a  # stable across turns

    def test_different_conversations_get_different_keys(self) -> None:
        a = stable_session_key(_request())
        b = stable_session_key(
            _request(messages=[{"role": "user", "content": "other convo"}])
        )
        assert a != b

    def test_key_is_opaque_hash(self) -> None:
        key = stable_session_key(_request(metadata={"user_id": "user-abc"}))
        assert key is not None
        assert "user-abc" not in key
        assert len(key) == 32
        int(key, 16)  # hex digest

    def test_returns_none_without_any_seed(self) -> None:
        assert stable_session_key(object()) is None


class TestCloudflareSessionAffinity:
    def test_build_request_body_sets_affinity_header(self) -> None:
        request = _request(metadata={"user_id": "user-abc"})
        body = build_request_body(request, thinking_enabled=False)
        headers = body["extra_headers"]
        assert headers[SESSION_AFFINITY_HEADER] == stable_session_key(request)

    def test_affinity_header_stable_across_turns(self) -> None:
        first = build_request_body(_request(), thinking_enabled=False)
        later = build_request_body(
            _request(
                messages=[
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "more"},
                ]
            ),
            thinking_enabled=False,
        )
        assert (
            first["extra_headers"][SESSION_AFFINITY_HEADER]
            == later["extra_headers"][SESSION_AFFINITY_HEADER]
        )


class TestPromptCacheKeyHook:
    def test_disabled_by_default(self) -> None:
        from providers.base import ProviderConfig
        from providers.cloudflare_ai.client import CloudflareAiProvider

        provider = CloudflareAiProvider(
            ProviderConfig(api_key="k", base_url="http://localhost/ai/v1")
        )
        assert provider.include_prompt_cache_key is False
        body: dict = {"model": "m"}
        provider._apply_prompt_cache_key(body, _request())
        assert "prompt_cache_key" not in body

    def test_enabled_provider_adds_stable_key(self) -> None:
        from providers.base import ProviderConfig
        from providers.cloudflare_ai.client import CloudflareAiProvider

        class OptInProvider(CloudflareAiProvider):
            include_prompt_cache_key = True

        provider = OptInProvider(
            ProviderConfig(api_key="k", base_url="http://localhost/ai/v1")
        )
        request = _request(metadata={"user_id": "user-abc"})
        body: dict = {"model": "m"}
        provider._apply_prompt_cache_key(body, request)
        assert body["prompt_cache_key"] == stable_session_key(request)

        # Never overwrites a caller-provided value.
        body = {"model": "m", "prompt_cache_key": "caller-key"}
        provider._apply_prompt_cache_key(body, request)
        assert body["prompt_cache_key"] == "caller-key"
