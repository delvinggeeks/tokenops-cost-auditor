"""Finding model + estimator helpers (FR-13, FR-22). Money math — 100% coverage
required; changes require golden-file update + spreadsheet diff (CLAUDE.md rule 4).

FR-22: EvidenceRef carries counts and metadata ONLY — never prompt/completion text.
Conservative estimation rules are documented here and in the report methodology
appendix; defaults of record live in tests/fixtures/pricing_golden_NOTES.md.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import pandas as pd

MAX_EVIDENCE = 20  # FR-13

# Severity-by-monthly-impact thresholds (USD) for impact-scaled detectors (D2/D3/D6).
# D4 uses the LLD rule (high if any window >= 10) and D5 is informational.
SEVERITY_HIGH_USD = 500.0
SEVERITY_MED_USD = 50.0


class Severity(enum.StrEnum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class Confidence(enum.StrEnum):
    CONSERVATIVE = "conservative"
    ESTIMATED = "estimated"


@dataclass(frozen=True)
class EvidenceRef:
    """Counts/metadata only (FR-22): no text field may ever be added here."""

    row_idx: int
    ts: str  # ISO-8601 UTC
    model: str
    tokens: int  # prompt+completion of the referenced call
    note: str  # short fixed-vocabulary annotation, never log content


@dataclass(frozen=True)
class Finding:
    id: str
    detector: str
    severity: Severity
    monthly_cost_impact_usd: float
    confidence: Confidence
    fix_text: str
    evidence: tuple[EvidenceRef, ...] = field(default=())
    # R-D6-AGG: per-run/per-cluster breakdown of an aggregated finding, carried
    # into report.json only (renderers show the aggregate). Counts and
    # timestamps only — FR-22 applies here exactly as it does to evidence.
    detail: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if len(self.evidence) > MAX_EVIDENCE:
            raise ValueError(f"evidence exceeds {MAX_EVIDENCE} items (FR-13/FR-22)")


def sample_evidence_across(
    chunks: list[pd.DataFrame], note: str, limit: int = MAX_EVIDENCE
) -> tuple[EvidenceRef, ...]:
    """R-D6-AGG: evidence for an aggregated finding samples ACROSS its
    constituent runs/clusters instead of exhausting the cap on the first one."""
    per_chunk = max(1, limit // max(len(chunks), 1))
    sampled = pd.concat([c.head(per_chunk) for c in chunks]).sort_values("ts").head(limit)
    return make_evidence(sampled, note=note, limit=limit)


def observed_days(frame: pd.DataFrame) -> int:
    """Distinct UTC dates in the frame, min 1 (accepted default Q7)."""
    if len(frame) == 0:
        return 1
    return max(int(frame["ts"].dt.date.nunique()), 1)


def monthly_factor(days: int) -> float:
    """Observed-window waste -> monthly impact: x 30/observed_days (Q7)."""
    return 30.0 / max(days, 1)


def effective_prompt_rate(row: pd.Series, rate: object) -> float:
    """USD per 1M prompt tokens as this row was ACTUALLY billed: uncached
    tokens at the input rate, cache reads at the cache_read rate, cache writes
    at the cache_write rate (R-Q4 total-prompt semantics).

    Equals rate.input exactly for uncached traffic — the D3/D6 goldens are
    invariant by construction. On cache-heavy agent traffic (the ICP), pricing
    removed prompt tokens at the flat input rate inflated savings ~10x and
    produced >100% savings claims (UAT-1 dogfood fix, D11; money-math default
    recorded in pricing_golden_NOTES.md)."""
    prompt = int(row["prompt_tokens"])
    if prompt <= 0:
        return float(rate.input)  # type: ignore[attr-defined]
    cached = int(row["cached_tokens"])
    written = int(row["cache_write_tokens"])
    uncached = max(prompt - cached - written, 0)
    return (
        uncached * float(rate.input)  # type: ignore[attr-defined]
        + cached * float(rate.cache_read)  # type: ignore[attr-defined]
        + written * float(rate.cache_write)  # type: ignore[attr-defined]
    ) / prompt


def severity_for_impact(monthly_usd: float) -> Severity:
    if monthly_usd >= SEVERITY_HIGH_USD:
        return Severity.HIGH
    if monthly_usd >= SEVERITY_MED_USD:
        return Severity.MED
    return Severity.LOW


def make_evidence(
    rows: pd.DataFrame, note: str, limit: int = MAX_EVIDENCE
) -> tuple[EvidenceRef, ...]:
    """Sample up to `limit` rows into EvidenceRefs — counts and metadata only."""
    refs = []
    for idx, row in rows.head(limit).iterrows():
        refs.append(
            EvidenceRef(
                row_idx=int(idx),
                ts=row["ts"].isoformat(),
                model=str(row["model"]),
                tokens=int(row["prompt_tokens"]) + int(row["completion_tokens"]),
                note=note,
            )
        )
    return tuple(refs)
