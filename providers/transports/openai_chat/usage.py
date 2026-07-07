"""Map OpenAI-compat streamed usage to Anthropic usage fields.

Providers report actual token accounting in the final stream chunk's ``usage``
object. Cached-prompt tokens arrive in two shapes:

- OpenAI / Cloudflare / Groq / Z.ai / Kimi: ``prompt_tokens_details.cached_tokens``
- DeepSeek: top-level ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``

Anthropic protocol semantics: ``usage.input_tokens`` counts *non-cached* input
and ``usage.cache_read_input_tokens`` counts tokens served from the provider
prompt cache. Forwarding these keeps Claude Code's ``/cost``, ``/context``,
and auto-compact triggers accurate instead of relying on local estimates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


@dataclass(frozen=True)
class ProviderStreamUsage:
    """Provider-reported token usage for one completed stream."""

    prompt_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None

    @property
    def anthropic_input_tokens(self) -> int | None:
        """Non-cached input tokens per Anthropic usage semantics."""
        if self.prompt_tokens is None:
            return None
        if self.cache_read_input_tokens:
            return max(self.prompt_tokens - self.cache_read_input_tokens, 0)
        return self.prompt_tokens


def extract_provider_stream_usage(usage_info: Any) -> ProviderStreamUsage:
    """Extract usage counters from an OpenAI-compat ``usage`` object or mapping."""
    if usage_info is None:
        return ProviderStreamUsage()

    prompt_tokens = _int_or_none(_field(usage_info, "prompt_tokens"))
    output_tokens = _int_or_none(_field(usage_info, "completion_tokens"))

    cached = None
    details = _field(usage_info, "prompt_tokens_details")
    if details is not None:
        cached = _int_or_none(_field(details, "cached_tokens"))
    if cached is None:
        # DeepSeek shape: prompt_tokens == cache_hit + cache_miss.
        cached = _int_or_none(_field(usage_info, "prompt_cache_hit_tokens"))

    return ProviderStreamUsage(
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cached if cached else None,
    )
