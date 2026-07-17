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

    def __post_init__(self) -> None:
        if len(self.evidence) > MAX_EVIDENCE:
            raise ValueError(f"evidence exceeds {MAX_EVIDENCE} items (FR-13/FR-22)")


def observed_days(frame: pd.DataFrame) -> int:
    """Distinct UTC dates in the frame, min 1 (accepted default Q7)."""
    if len(frame) == 0:
        return 1
    return max(int(frame["ts"].dt.date.nunique()), 1)


def monthly_factor(days: int) -> float:
    """Observed-window waste -> monthly impact: x 30/observed_days (Q7)."""
    return 30.0 / max(days, 1)


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
