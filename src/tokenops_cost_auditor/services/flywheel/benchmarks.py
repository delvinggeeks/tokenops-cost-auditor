"""M-FLY-1 B1 — L1 peer-benchmark percentiles (docs/12 Stage 3, Track B).

NO NEW MONEY MATH: the ranked value is the engine's own Audit.savings_pct
(each company's waste share of spend, computed deterministically at audit
time). Benchmarks RANK existing numbers; they never recompute a dollar.
The ranking method itself is money-adjacent and golden-pinned
(tests/fixtures/pricing_golden_NOTES.md, 12-customer derivation).

METHOD (the NOTES-sheet fact): nearest-rank inclusive percentile —
    p(c) = round(100 * |{v in cohort : v <= v_c}| / n)
cohort = latest DONE audit's savings_pct per INCLUDED customer
(benchmark_sharing honored at the source, R-F1), n counted WITH the
requesting customer. Lower = leaner.

HONESTY LAW: live only at n >= flywheel_l1_min_customers; every rendered
number carries "based on N companies". Below threshold the surface is NOT
RENDERED — absence, never a countdown (zero-state law).

LEAKAGE LAW: the public result is {percentile, n}. Never another
company's value, never the distribution, never a cohort statistic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, User


@dataclass(frozen=True)
class Benchmark:
    live: bool
    n: int  # cohort size behind the number (printed when live)
    percentile: int | None  # nearest-rank inclusive; lower = leaner
    reason: str  # honest why-not when not live (internal, never rendered)


def _aware(dt: datetime) -> datetime:
    # legacy/naive rows normalize at read (cold-review M-FLY-1 f.3) — never a
    # suppressed comparison that could TypeError in prod
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _included(session: Session) -> set[str]:
    return {
        u.id for u in session.execute(select(User)).scalars() if u.benchmark_sharing is not False
    }


def _cohort(session: Session, included: set[str]) -> dict[str, float]:
    """Latest done audit's savings_pct per INCLUDED customer. Deterministic:
    candidates sort on (when, id) and later entries overwrite — identical
    timestamps resolve by id, never by DB return order (cold f.2)."""
    candidates = [
        a
        for a in session.execute(select(Audit).where(Audit.status == "done")).scalars()
        if a.user_id in included and a.savings_pct is not None
    ]
    candidates.sort(key=lambda a: (_aware(a.report_ready_at or a.created_at), a.id))
    cohort: dict[str, float] = {}
    for a in candidates:
        cohort[a.user_id] = float(cast(float, a.savings_pct))
    return cohort


def waste_percentile(
    session: Session, settings: Settings, user_id: str, own_value: float | None = None
) -> Benchmark:
    """POLICY (cold f.1, both ingestion paths identical): n counts the
    requester — self-INCLUSIVE, as the NOTES derivation states. Callers
    reporting an in-flight audit pass own_value (the audit's own
    savings_pct) explicitly; it is authoritative over any stale DB row, so
    neither flush timing nor finalization order can change a rank."""
    included = _included(session)  # ONE scan (cold re-gate c): cohort + guard share it
    cohort = _cohort(session, included)
    if own_value is not None and user_id in included:
        cohort[user_id] = float(own_value)
    mine = cohort.get(user_id)
    if mine is None:
        # own toggle off, or no audited waste share yet — either way, no rank
        return Benchmark(live=False, n=len(cohort), percentile=None, reason="not in cohort")
    n = len(cohort)
    if n < settings.flywheel_l1_min_customers:
        return Benchmark(live=False, n=n, percentile=None, reason="below threshold")
    at_or_below = sum(1 for v in cohort.values() if v <= mine)
    return Benchmark(
        live=True,
        n=n,
        percentile=round(100 * at_or_below / n),
        reason="",
    )


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


REPORT_BLOCK_KEYS = frozenset({"percentile", "label", "based_on_companies", "method"})


def report_block(
    session: Session, settings: Settings, user_id: str, own_value: float | None = None
) -> dict[str, object] | None:
    """M-FLY-1 B1b: the report's benchmark block, or None (dormant = the key
    never exists — absent fixtures stay byte-identical, zero-state law).
    LEAKAGE LAW: REPORT_BLOCK_KEYS is exhaustive and test-pinned — nothing
    else can ride into a customer-visible report from the cohort."""
    b = waste_percentile(session, settings, user_id, own_value=own_value)
    if not b.live or b.percentile is None:
        return None
    return {
        "percentile": b.percentile,
        "label": ordinal(b.percentile),
        "based_on_companies": b.n,
        "method": (
            "nearest-rank inclusive over each company's own audited waste share; lower is leaner"
        ),
    }
