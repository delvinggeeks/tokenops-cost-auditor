"""Detector protocol + shared context (docs/02-HLD.md C4; docs/03-LLD.md §3).

Pure functions over CallRecordFrames: no I/O, no network (NFR-01, T-NFR-01).
Detectors run on frames AFTER coster.apply (cost_usd present).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.rules.findings import Finding


@dataclass(frozen=True)
class DetectorContext:
    settings: Settings
    table: PricingTable
    observed_days: int


class Detector(Protocol):
    name: str

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]: ...


def split_on_gap(group: pd.DataFrame, gap_s: int) -> list[pd.DataFrame]:
    """Session splitter (R-D6-AGG): time-ordered rows split where the gap to
    the previous row exceeds gap_s. Shared by D6 and D4 so 'session' means the
    same thing in both aggregations."""
    ordered = group.sort_values("ts")
    out: list[pd.DataFrame] = []
    start = 0
    times = ordered["ts"].tolist()
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[i - 1]).total_seconds() > gap_s:
            out.append(ordered.iloc[start:i])
            start = i
    return out


def ttl_window_s(settings: Settings, provider: str, model: str) -> int:
    """Founder correction C4: TTL windows per provider-family, never one global.
    Longest matching key wins (keys match provider name or a model-id prefix);
    fallback is D2_TTL_WINDOW_S."""
    provider = provider.lower()
    model = model.lower()
    matches = [
        key
        for key in settings.d2_ttl_windows
        if provider == key.lower() or model.startswith(key.lower())
    ]
    if not matches:
        return settings.d2_ttl_window_s
    return settings.d2_ttl_windows[max(matches, key=len)]
