"""Normalizer: RawRow stream -> CallRecordFrame (FR-02; columns per docs/03-LLD.md §2,
plus cache_write_tokens added under founder ruling R-Q4 for four-rate costing).

FR-22 invariant: prompt text, when present in logs, is used ONLY to compute
prefix_hash in memory and is dropped before the frame is built. raw_extra carries
unknown scalar fields only — never text bodies.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from tokenops_cost_auditor.services.ingest.base import RawRow

COLUMNS = (
    "ts",
    "provider",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "cache_write_tokens",
    "latency_ms",
    "endpoint",
    "request_id",
    "tag",
    "prefix_hash",
    "declared_max_tokens",
    "raw_extra",
)

TEXT_KEYS = frozenset(
    {
        "_text",
        "prompt",
        "completion",
        "messages",
        "content",
        "text",
        "system",
        "input",
        "output",
        "choices",
        "response_text",
        "prompt_text",
        "completion_text",
    }
)


@dataclass
class RowError:
    line_no: int
    reason: str


@dataclass
class NormalizeResult:
    frame: pd.DataFrame
    row_errors: list[RowError] = field(default_factory=list)
    total_rows: int = 0


def prefix_hash(text: str, chars: int) -> str:
    """SHA-256 hex over the first `chars` characters (ADR-7, R-Q6 default 4096)."""
    return hashlib.sha256(text[:chars].encode("utf-8", errors="replace")).hexdigest()


def _coerce_ts(value: object) -> datetime | None:
    """UTC coercion (NFR-11, T-ING-07): epoch seconds or ISO-8601; naive -> UTC."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value <= 0:
            return None
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            try:
                return _coerce_ts(float(value.strip()))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _cache_field(data: dict[str, object], key: str) -> tuple[int | None, str | None]:
    """Cache fields: absent means 0, but a PRESENT-yet-unparseable/negative value is
    a row error, never a silent 0 — zeroed cache counts corrupt cost math and the
    D2 missing-cache detector (G2 cold-reviewer finding 1)."""
    value = data.get(key)
    if value is None:
        return 0, None
    coerced = _coerce_int(value)
    if coerced is None or coerced < 0:
        return None, f"invalid {key}"
    return coerced, None


def normalize(rows: Iterable[RawRow], prefix_hash_chars: int = 4096) -> NormalizeResult:
    records: list[dict[str, object]] = []
    errors: list[RowError] = []
    total = 0

    for row in rows:
        total += 1
        if row.data is None:
            errors.append(RowError(row.line_no, row.error or "unparseable row"))
            continue
        data = row.data

        ts = _coerce_ts(data.get("ts"))
        model = data.get("model")
        prompt_tokens = _coerce_int(data.get("prompt_tokens"))
        completion_tokens = _coerce_int(data.get("completion_tokens"))

        cached, cached_err = _cache_field(data, "cached_tokens")
        cache_write, cache_write_err = _cache_field(data, "cache_write_tokens")

        reason: str | None = None
        if ts is None:
            reason = "missing or invalid timestamp"
        elif not isinstance(model, str) or not model:
            reason = "missing model"
        elif prompt_tokens is None or prompt_tokens < 0:
            reason = "missing or invalid prompt_tokens"
        elif completion_tokens is None or completion_tokens < 0:
            reason = "missing or invalid completion_tokens"
        elif cached_err or cache_write_err:
            reason = cached_err or cache_write_err
        if reason is not None:
            errors.append(RowError(row.line_no, reason))
            continue
        assert ts is not None and prompt_tokens is not None and completion_tokens is not None
        assert cached is not None and cache_write is not None

        text = data.get("_text")
        computed_hash: str | None = None
        if isinstance(text, str) and text:
            computed_hash = prefix_hash(text, prefix_hash_chars)
        elif isinstance(data.get("prefix_hash"), str) and data.get("prefix_hash"):
            computed_hash = str(data["prefix_hash"])

        extra = data.get("_extra") if isinstance(data.get("_extra"), dict) else {}
        assert isinstance(extra, dict)
        raw_extra = {k: v for k, v in extra.items() if k.lower() not in TEXT_KEYS}

        records.append(
            {
                "ts": ts,
                "provider": str(data.get("provider", "generic")),
                "model": str(model),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cached,
                "cache_write_tokens": cache_write,
                "latency_ms": _coerce_float(data.get("latency_ms")),
                "endpoint": str(data.get("endpoint") or ""),
                "request_id": str(data.get("request_id") or f"r{row.line_no}"),
                "tag": str(data.get("tag") or ""),
                "prefix_hash": computed_hash,
                "declared_max_tokens": _coerce_int(data.get("declared_max_tokens")),
                "raw_extra": raw_extra,
            }
        )

    frame = pd.DataFrame(records, columns=list(COLUMNS))
    if len(frame):
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        for col in ("prompt_tokens", "completion_tokens", "cached_tokens", "cache_write_tokens"):
            frame[col] = frame[col].astype("int64")
        frame["latency_ms"] = frame["latency_ms"].astype("float64")
        frame["declared_max_tokens"] = frame["declared_max_tokens"].astype("float64")
    return NormalizeResult(frame=frame, row_errors=errors, total_rows=total)
