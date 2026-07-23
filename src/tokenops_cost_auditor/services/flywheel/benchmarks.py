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


def _cohort(session: Session) -> dict[str, float]:
    """Latest done audit's savings_pct per INCLUDED customer."""
    included = {
        u.id for u in session.execute(select(User)).scalars() if u.benchmark_sharing is not False
    }
    latest: dict[str, tuple[object, float]] = {}
    for a in session.execute(select(Audit).where(Audit.status == "done")).scalars():
        if a.user_id not in included or a.savings_pct is None:
            continue
        when = a.report_ready_at or a.created_at
        held = latest.get(a.user_id)
        if held is None or when > held[0]:  # type: ignore[operator]
            latest[a.user_id] = (when, float(a.savings_pct))
    return {uid: val for uid, (_, val) in latest.items()}


def waste_percentile(session: Session, settings: Settings, user_id: str) -> Benchmark:
    cohort = _cohort(session)
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


def report_block(session: Session, settings: Settings, user_id: str) -> dict[str, object] | None:
    """M-FLY-1 B1b: the report's benchmark block, or None (dormant = the key
    never exists — absent fixtures stay byte-identical, zero-state law).
    LEAKAGE LAW: REPORT_BLOCK_KEYS is exhaustive and test-pinned — nothing
    else can ride into a customer-visible report from the cohort."""
    b = waste_percentile(session, settings, user_id)
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
