"""Anthropic JSONL export parser (FR-01/FR-02).

Accepted line shapes (one JSON object per line):
1. A Messages API response object:
   {"id": "msg_...", "type": "message", "model": "claude-...",
    "usage": {"input_tokens": N, "cache_creation_input_tokens": N,
    "cache_read_input_tokens": N, "output_tokens": N}, ...}
2. A logged wrapper: {"request_id"|..., "ts"|"timestamp": ..., "endpoint": ...,
    "tag": ..., "request": {"max_tokens": N, "system": ..., "messages": [...]},
    "response": {<shape 1>}}

Token semantics normalized to TokenOps convention (R-Q4): prompt_tokens = TOTAL
input = input_tokens + cache_read + cache_creation (Anthropic reports them
disjointly); cached_tokens = cache_read_input_tokens;
cache_write_tokens = cache_creation_input_tokens.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from tokenops_cost_auditor.services.ingest.base import RawRow, iter_jsonl


def _intlike(value: object) -> int | None:
    """int or integral float -> int; anything else (incl. bool) -> None.
    Never silently zeroes a malformed count (G2 cold-reviewer finding 2)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


class AnthropicJsonlParser:
    name = "anthropic_jsonl"
    provider = "anthropic"

    def sniff(self, sample_lines: list[str]) -> bool:
        for line in sample_lines:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            body = obj.get("response", obj)
            if not isinstance(body, dict):
                continue
            usage = body.get("usage")
            if body.get("type") == "message" or (
                isinstance(usage, dict) and "input_tokens" in usage
            ):
                return True
        return False

    def parse(self, path: Path) -> Iterator[RawRow]:
        for row in iter_jsonl(path):
            if row.data is None:
                yield row
                continue
            yield RawRow(row.line_no, self._extract(row.data))

    def _extract(self, obj: dict[str, object]) -> dict[str, object]:
        body = obj.get("response") if isinstance(obj.get("response"), dict) else obj
        assert isinstance(body, dict)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        request = obj.get("request") if isinstance(obj.get("request"), dict) else {}
        assert isinstance(request, dict)

        base_input = _intlike(usage.get("input_tokens"))
        cache_read = _intlike(usage.get("cache_read_input_tokens", 0))
        cache_write = _intlike(usage.get("cache_creation_input_tokens", 0))
        # Any malformed component invalidates the total -> normalizer rejects the
        # row ("missing or invalid prompt_tokens") instead of undercounting.
        prompt_total = (
            base_input + cache_read + cache_write
            if base_input is not None and cache_read is not None and cache_write is not None
            else None
        )

        known = {
            "response",
            "request",
            "request_id",
            "ts",
            "timestamp",
            "endpoint",
            "tag",
            "user",
            "latency_ms",
            "metadata",
            "id",
            "type",
            "role",
            "model",
            "usage",
            "content",
            "stop_reason",
            "stop_sequence",
        }
        return {
            "provider": self.provider,
            "model": body.get("model"),
            "ts": obj.get("ts") or obj.get("timestamp") or body.get("ts"),
            "prompt_tokens": prompt_total,
            "completion_tokens": usage.get("output_tokens"),
            "cached_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "request_id": obj.get("request_id") or body.get("id"),
            "endpoint": obj.get("endpoint", ""),
            "tag": obj.get("tag") or "",
            "latency_ms": obj.get("latency_ms"),
            "declared_max_tokens": request.get("max_tokens"),
            "_text": _prompt_text(request),
            "_extra": {
                k: v
                for k, v in obj.items()
                if k not in known and isinstance(v, str | int | float | bool)
            },
        }


def _prompt_text(request: dict[str, object]) -> str | None:
    """System + message content for in-memory prefix hashing only (ADR-7, FR-22)."""
    parts: list[str] = []
    if isinstance(request.get("system"), str):
        parts.append(str(request["system"]))
    messages = request.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                parts.append(str(msg["content"]))
    return "\n".join(parts) if parts else None
