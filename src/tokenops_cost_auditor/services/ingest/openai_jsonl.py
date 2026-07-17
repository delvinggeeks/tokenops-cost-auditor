"""OpenAI JSONL export parser (FR-01/FR-02).

Accepted line shapes (one JSON object per line):
1. A chat-completion response object:
   {"id": "chatcmpl-...", "object": "chat.completion", "created": <epoch>,
    "model": "gpt-...", "usage": {"prompt_tokens": N, "completion_tokens": N,
    "prompt_tokens_details": {"cached_tokens": N}}, ...}
2. A logged request/response wrapper:
   {"request_id": ..., "ts"|"timestamp"|"created": ..., "endpoint": ...,
    "tag"|"user"|"metadata": ..., "request": {"max_tokens": N, "messages": [...]},
    "response": {<shape 1>}}

Token semantics normalized downstream: prompt_tokens is the TOTAL input count
(OpenAI already includes cached tokens in prompt_tokens); cached_tokens is the
cached subset from prompt_tokens_details.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from tokenops_cost_auditor.services.ingest.base import RawRow, iter_jsonl


class OpenAIJsonlParser:
    name = "openai_jsonl"
    provider = "openai"

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
            obj_type = str(body.get("object", ""))
            if (isinstance(usage, dict) and "prompt_tokens" in usage) or (
                "chat.completion" in obj_type
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
        details = (
            usage.get("prompt_tokens_details")
            if isinstance(usage.get("prompt_tokens_details"), dict)
            else {}
        )
        assert isinstance(details, dict)
        request = obj.get("request") if isinstance(obj.get("request"), dict) else {}
        assert isinstance(request, dict)

        out: dict[str, object] = {
            "provider": self.provider,
            "model": body.get("model"),
            "ts": obj.get("ts") or obj.get("timestamp") or body.get("created"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_tokens": details.get("cached_tokens", 0),
            # OpenAI response usage does not expose cache-WRITE token counts, but
            # the GPT-5.6 family bills writes at 1.25x input (founder correction C1).
            # A wrapper-level cache_write_tokens field is honored when the customer's
            # logger supplies it; otherwise 0 — a TRACKED GAP recorded in
            # pricing_golden_NOTES.md (premium priced; engages via wrapper field or
            # the generic CSV contract, which carries cache_write_tokens natively).
            "cache_write_tokens": obj.get("cache_write_tokens", 0),
            "request_id": obj.get("request_id") or body.get("id"),
            "endpoint": obj.get("endpoint", ""),
            "tag": obj.get("tag") or obj.get("user") or "",
            "latency_ms": obj.get("latency_ms"),
            "declared_max_tokens": request.get("max_tokens"),
            # counts-only logging shippers may precompute the hash client-side
            # (same contract as generic CSV); text, when present, wins downstream
            "prefix_hash": obj.get("prefix_hash"),
            "_text": _prompt_text(request),
        }
        known = {
            "prefix_hash",
            "cache_write_tokens",
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
            "object",
            "created",
            "model",
            "usage",
            "choices",
            "system_fingerprint",
            "service_tier",
        }
        # Unknown scalar fields only (FR-02 raw_extra); nested bodies never carried.
        out["_extra"] = {
            k: v
            for k, v in obj.items()
            if k not in known and isinstance(v, str | int | float | bool)
        }
        return out


def _prompt_text(request: dict[str, object]) -> str | None:
    """Concatenate logged message content for in-memory prefix hashing only (ADR-7).
    The returned text is NEVER persisted (FR-22) — the normalizer hashes and drops it."""
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            parts.append(str(msg["content"]))
    return "\n".join(parts) if parts else None
