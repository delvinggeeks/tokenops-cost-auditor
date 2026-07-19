"""Connector contract (docs/12 Stage 1): every tier lands in the same shape.

A pull produces UsageBucket rows (day x model, counts only — FR-22 applies
at this door: no prompt/completion text exists in provider usage APIs and
none may ever be added here) plus PullStats, the dedup/provenance record
printed on every pull (UAT-D5 law analog for T2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


class SupportsGet(Protocol):
    """The slice of httpx.Client the fetchers use — lets tests inject a fake."""

    def get(self, url: str, *, params: Any, headers: Any) -> Any: ...


@dataclass(frozen=True)
class UsageBucket:
    day: date
    model: str
    calls: int
    prompt_tokens: int  # uncached + cached input
    completion_tokens: int
    cached_tokens: int
    cost_usd: float | None = None  # provider-reported, when present


@dataclass
class PullStats:
    provider: str
    endpoint: str
    pages: int = 0
    buckets_in: int = 0
    upserted: int = 0
    updated_existing: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"pull[{self.provider}]: pages={self.pages} buckets_in={self.buckets_in} "
            f"upserted={self.upserted} updated_existing={self.updated_existing}"
        )
