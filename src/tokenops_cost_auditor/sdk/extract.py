"""Response -> usage record. THE FR-22 BOUNDARY of the SDK (S-1).

These functions read ONLY the `usage`, `model`, and timing off a provider
response object. They never touch `choices`, `content`, `messages`, or any
field that could carry prompt or completion text — so a record built here
CANNOT contain customer content, by construction. The SDK's own test suite
proves this by feeding responses whose text fields are populated and
asserting the built record has none of it.

Composition matches the platform's contract (verified against the provider
SDKs, 2026-07-23):
  OpenAI chat.completions: prompt_tokens is TOTAL input (cached included);
    cached from usage.prompt_tokens_details.cached_tokens.
  Anthropic messages: input_tokens EXCLUDES cache, so
    prompt_tokens = input + cache_read + cache_creation (the anthropic_usage
    composition), cached = cache_read, cache_write = cache_creation.
Only allowlisted generic-contract fields are emitted (the /api/v1/ingest
door rejects anything else, loudly).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except TypeError, ValueError:
        return 0


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """usage objects are pydantic models OR dicts depending on SDK version."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _base(model: Any, endpoint: str, latency_s: float, tag: str) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "model": str(model or "unknown")[:120],
        "endpoint": endpoint,
        "latency_ms": round(max(latency_s, 0.0) * 1000, 1),
    }
    if tag:
        rec["tag"] = tag[:120]
    return rec


def extract_openai(response: Any, latency_s: float, tag: str = "") -> dict[str, Any] | None:
    """OpenAI chat.completions response -> record. None if no usage present.

    Reads response.usage + response.model ONLY — never response.choices."""
    usage = _attr(response, "usage")
    if usage is None:
        return None
    details = _attr(usage, "prompt_tokens_details")
    rec = _base(_attr(response, "model"), "openai.chat.completions", latency_s, tag)
    rec.update(
        {
            "provider": "openai",
            "prompt_tokens": _int(_attr(usage, "prompt_tokens")),
            "completion_tokens": _int(_attr(usage, "completion_tokens")),
            "cached_tokens": _int(_attr(details, "cached_tokens")),
        }
    )
    return rec


def extract_anthropic(response: Any, latency_s: float, tag: str = "") -> dict[str, Any] | None:
    """Anthropic messages response -> record. None if no usage present.

    Reads response.usage + response.model ONLY — never response.content."""
    usage = _attr(response, "usage")
    if usage is None:
        return None
    inp = _int(_attr(usage, "input_tokens"))
    cache_read = _int(_attr(usage, "cache_read_input_tokens"))
    cache_creation = _int(_attr(usage, "cache_creation_input_tokens"))
    rec = _base(_attr(response, "model"), "anthropic.messages", latency_s, tag)
    rec.update(
        {
            "provider": "anthropic",
            # input_tokens EXCLUDES cache (anthropic semantics) — total it up
            "prompt_tokens": inp + cache_read + cache_creation,
            "completion_tokens": _int(_attr(usage, "output_tokens")),
            "cached_tokens": cache_read,
            "cache_write_tokens": cache_creation,
        }
    )
    return rec
