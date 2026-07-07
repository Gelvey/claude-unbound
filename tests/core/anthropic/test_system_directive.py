"""Concise-output directive: append-only, cache-safe, idempotent."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from api.models.anthropic import MessagesRequest, SystemContent
from config.settings import DEFAULT_CONCISE_OUTPUT_DIRECTIVE, Settings
from core.anthropic.system_directive import append_system_directive

_DIRECTIVE = "Be concise."


def _request(system: Any = None) -> MessagesRequest:
    payload: dict[str, Any] = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "hello"}],
    }
    if system is not None:
        payload["system"] = system
    return MessagesRequest.model_validate(payload)


def _system_blocks(request: MessagesRequest) -> list:
    system = request.system
    assert isinstance(system, list)
    return system


class TestAppendSystemDirective:
    def test_none_system_becomes_directive(self) -> None:
        request = _request()
        append_system_directive(request, _DIRECTIVE)
        assert request.system == _DIRECTIVE

    def test_string_system_gets_appended_suffix(self) -> None:
        request = _request(system="You are helpful.")
        append_system_directive(request, _DIRECTIVE)
        assert request.system == f"You are helpful.\n\n{_DIRECTIVE}"

    def test_block_list_gets_new_trailing_text_block(self) -> None:
        request = _request(
            system=[
                {
                    "type": "text",
                    "text": "You are helpful.",
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
        original_first = _system_blocks(request)[0]
        append_system_directive(request, _DIRECTIVE)
        blocks = _system_blocks(request)
        assert len(blocks) == 2
        # Existing blocks (and their cache_control breakpoints) are untouched.
        assert blocks[0] is original_first
        assert getattr(blocks[0], "cache_control", None) == {"type": "ephemeral"}
        last = blocks[1]
        assert isinstance(last, SystemContent)
        assert last.text == _DIRECTIVE
        assert getattr(last, "cache_control", None) is None

    def test_appended_block_matches_existing_block_shape(self) -> None:
        # Plain dict blocks stay dicts; model blocks get a model appended.
        request = SimpleNamespace(system=[{"type": "text", "text": "sys"}])
        append_system_directive(request, _DIRECTIVE)
        assert request.system[1] == {"type": "text", "text": _DIRECTIVE}

    def test_idempotent_on_string_system(self) -> None:
        request = _request(system="You are helpful.")
        append_system_directive(request, _DIRECTIVE)
        once = request.system
        append_system_directive(request, _DIRECTIVE)
        assert request.system == once

    def test_idempotent_on_block_list_system(self) -> None:
        request = _request(system=[{"type": "text", "text": "You are helpful."}])
        append_system_directive(request, _DIRECTIVE)
        append_system_directive(request, _DIRECTIVE)
        assert len(_system_blocks(request)) == 2

    def test_empty_or_whitespace_directive_is_noop(self) -> None:
        request = _request(system="You are helpful.")
        append_system_directive(request, "")
        append_system_directive(request, "   \n")
        assert request.system == "You are helpful."


class TestSettings:
    def test_concise_output_defaults_on(self) -> None:
        settings = Settings()
        assert settings.concise_output is True
        assert settings.concise_output_directive == DEFAULT_CONCISE_OUTPUT_DIRECTIVE

    def test_empty_directive_env_falls_back_to_builtin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CONCISE_OUTPUT_DIRECTIVE", "   ")
        settings = Settings()
        assert settings.concise_output_directive == DEFAULT_CONCISE_OUTPUT_DIRECTIVE

    def test_custom_directive_env_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CONCISE_OUTPUT_DIRECTIVE", "Short answers only.")
        settings = Settings()
        assert settings.concise_output_directive == "Short answers only."


class TestPipelineApplication:
    def _service_and_routed(self, settings: Settings):
        from unittest.mock import MagicMock

        from api.request_pipeline import ApiRequestPipeline

        mock_provider = MagicMock()

        async def fake_stream(*_a, **_kw):
            yield "event: ping\ndata: {}\n\n"

        mock_provider.stream_response = fake_stream
        service = ApiRequestPipeline(settings, provider_getter=lambda _: mock_provider)
        routed = service._model_router.resolve_messages_request(
            _request(system="You are Claude Code.")
        )
        return service, routed

    def test_provider_stream_appends_directive_when_enabled(self) -> None:
        settings = Settings()
        assert settings.concise_output is True
        service, routed = self._service_and_routed(settings)
        service._provider_stream(
            routed,
            wire_api="messages",
            raw_log_label="FULL_PAYLOAD",
            raw_log_payload=dict,
        )
        assert isinstance(routed.request.system, str)
        assert routed.request.system.startswith("You are Claude Code.")
        assert routed.request.system.endswith(settings.concise_output_directive)

    def test_provider_stream_leaves_system_untouched_when_disabled(self) -> None:
        settings = Settings()
        settings.concise_output = False
        service, routed = self._service_and_routed(settings)
        service._provider_stream(
            routed,
            wire_api="messages",
            raw_log_label="FULL_PAYLOAD",
            raw_log_payload=dict,
        )
        assert routed.request.system == "You are Claude Code."

    def test_directive_counted_in_input_tokens(self) -> None:
        """Directive is applied before token counting, so estimates include it."""
        from unittest.mock import MagicMock

        from api.request_pipeline import ApiRequestPipeline

        seen_systems: list = []

        def counting_counter(messages, system, tools) -> int:
            seen_systems.append(system)
            return 1

        mock_provider = MagicMock()

        async def fake_stream(*_a, **_kw):
            yield "event: ping\ndata: {}\n\n"

        mock_provider.stream_response = fake_stream
        settings = Settings()
        service = ApiRequestPipeline(
            settings,
            provider_getter=lambda _: mock_provider,
            token_counter=counting_counter,
        )
        routed = service._model_router.resolve_messages_request(_request(system="sys"))
        service._provider_stream(
            routed,
            wire_api="messages",
            raw_log_label="FULL_PAYLOAD",
            raw_log_payload=dict,
        )
        assert len(seen_systems) == 1
        assert settings.concise_output_directive in str(seen_systems[0])
