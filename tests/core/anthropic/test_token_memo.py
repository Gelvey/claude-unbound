"""Token-count memoization: correctness, eviction bound, uncacheable inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.models.anthropic import Message, Tool
from core.anthropic import tokens
from core.anthropic.tokens import (
    clear_token_count_memo,
    get_token_count,
    token_count_memo_size,
)


@pytest.fixture(autouse=True)
def _fresh_memo():
    clear_token_count_memo()
    yield
    clear_token_count_memo()


def _messages(n: int = 3) -> list[Message]:
    out: list[Message] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        out.append(Message(role=role, content=f"turn {i}: some conversation text"))
    return out


def _tools() -> list[Tool]:
    return [
        Tool(
            name="get_weather",
            description="Get weather",
            input_schema={"type": "object", "properties": {}},
        )
    ]


class TestMemoCorrectness:
    def test_repeated_calls_return_identical_totals(self) -> None:
        messages = _messages()
        first = get_token_count(messages, system="You are helpful.", tools=_tools())
        second = get_token_count(messages, system="You are helpful.", tools=_tools())
        assert first == second
        assert token_count_memo_size() > 0

    def test_cached_total_matches_fresh_memo_total(self) -> None:
        messages = _messages()
        warm = get_token_count(messages, system="You are helpful.", tools=_tools())
        # Second call is served largely from cache.
        cached = get_token_count(messages, system="You are helpful.", tools=_tools())
        clear_token_count_memo()
        cold = get_token_count(messages, system="You are helpful.", tools=_tools())
        assert warm == cached == cold

    def test_appending_a_message_changes_total_consistently(self) -> None:
        messages = _messages()
        base = get_token_count(messages)
        longer = [*messages, Message(role="user", content="one more question")]
        extended = get_token_count(longer)
        assert extended > base
        clear_token_count_memo()
        assert get_token_count(longer) == extended

    def test_system_block_list_is_memoized(self) -> None:
        system = [{"type": "text", "text": "You are helpful."}]
        a = get_token_count(_messages(1), system=system)
        b = get_token_count(_messages(1), system=system)
        assert a == b

    def test_string_content_and_block_content_differ_in_keyspace(self) -> None:
        as_string = [Message(role="user", content="hello")]
        as_blocks = [
            Message.model_validate(
                {"role": "user", "content": [{"type": "text", "text": "hello"}]}
            )
        ]
        # Same text, but distinct message shapes must not collide in the memo.
        first = get_token_count(as_string)
        second = get_token_count(as_blocks)
        clear_token_count_memo()
        assert get_token_count(as_string) == first
        assert get_token_count(as_blocks) == second


class TestMemoEviction:
    def test_memo_size_stays_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tokens, "_TOKEN_MEMO_MAX_ENTRIES", 8)
        for i in range(50):
            get_token_count([Message(role="user", content=f"unique message {i}")])
        assert token_count_memo_size() <= 8

    def test_evicted_entries_are_recomputed_correctly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tokens, "_TOKEN_MEMO_MAX_ENTRIES", 4)
        message = [Message(role="user", content="stable message")]
        first = get_token_count(message)
        for i in range(20):
            get_token_count([Message(role="user", content=f"filler {i}")])
        assert get_token_count(message) == first


class TestUncacheableInputs:
    def test_non_serializable_message_still_counts(self) -> None:
        class _Weird:
            pass

        msg = SimpleNamespace(role="user", content=[_Weird()])
        total = get_token_count([msg])
        assert total >= 1
        # Fallback str() encoding of the block still contributes tokens via
        # the unknown-block path, but nothing gets memoized for it.
        clear_token_count_memo()
        assert get_token_count([msg]) == total

    def test_stable_key_material_rejects_unserializable(self) -> None:
        assert tokens._stable_key_material(object()) is None
        assert tokens._stable_key_material([object()]) is None
        assert tokens._stable_key_material("text") == "text"

    def test_memoized_count_bypasses_cache_for_none_key(self) -> None:
        calls: list[int] = []

        def compute() -> int:
            calls.append(1)
            return 7

        assert tokens._memoized_count("test", None, compute) == 7
        assert tokens._memoized_count("test", None, compute) == 7
        assert len(calls) == 2
        assert token_count_memo_size() == 0
