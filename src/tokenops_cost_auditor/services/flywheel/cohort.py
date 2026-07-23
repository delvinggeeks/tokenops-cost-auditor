"""M-FLY-0 A2 — the cohort ledger (Honesty Law plumbing, docs/12 Stage 3).

Answers ONE question: which learning rungs may exist yet? No model ships
below its data threshold, and every threshold lives in config — never
hard-coded into a rung. Counts honor benchmark_sharing (R-F1): an excluded
account contributes to no rung's n, because a benchmark may only ever be
computed from accounts that are actually in it.

Surfaces: the founder ops digest line and an admin row. Deliberately NO
customer-facing surface — customers meet a rung the day it goes live
(zero-state law), never a countdown.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, FindingFeedback, User


@dataclass(frozen=True)
class Rung:
    name: str
    n: int  # the population the rung keys on
    threshold: int
    live: bool
    note: str  # the honest one-phrase state


@dataclass(frozen=True)
class CohortStatus:
    customers_with_audit: int  # included accounts with >=1 done audit
    customers_with_labels: int  # included accounts with >=1 L0 verdict
    history_months: int  # whole months spanned by included done audits
    rungs: tuple[Rung, ...]

    def digest_line(self) -> str:
        states = " · ".join(f"{r.name} {r.note}" for r in self.rungs)
        return (
            f"Flywheel: {self.customers_with_audit} audited / "
            f"{self.customers_with_labels} labeled customer(s), "
            f"{self.history_months}mo history — {states}"
        )


def status(session: Session, settings: Settings) -> CohortStatus:
    included = {
        u.id for u in session.execute(select(User)).scalars() if u.benchmark_sharing is not False
    }
    done = [
        a
        for a in session.execute(select(Audit).where(Audit.status == "done")).scalars()
        if a.user_id in included
    ]
    audited_customers = {a.user_id for a in done}
    audit_ids = {a.id: a.user_id for a in done}
    labeled_customers = {
        audit_ids[fb.audit_id]
        for fb in session.execute(
            select(FindingFeedback).where(FindingFeedback.audit_id.in_(audit_ids))
        ).scalars()
        if fb.audit_id in audit_ids
    }
    months = 0
    if done:
        stamps = sorted((a.report_ready_at or a.created_at) for a in done)
        span = stamps[-1] - stamps[0]
        months = span.days // 30
    n_audit = len(audited_customers)
    n_label = len(labeled_customers)

    def rung(name: str, n: int, threshold: int, extra_ok: bool = True, extra: str = "") -> Rung:
        live = n >= threshold and extra_ok
        if live:
            note = "LIVE"
        else:
            need = max(threshold - n, 0)
            note = (
                f"dormant (needs {need} more{extra})" if need else f"dormant ({extra.strip(' +')})"
            )
        return Rung(name=name, n=n, threshold=threshold, live=live, note=note)

    rungs = (
        rung("L1 benchmarks", n_audit, settings.flywheel_l1_min_customers),
        rung("L2 calibration", n_label, settings.flywheel_l2_min_customers),
        rung(
            "L3 learned",
            n_audit,
            settings.flywheel_l3_min_customers,
            extra_ok=months >= settings.flywheel_l3_min_history_months,
            extra=f" + {settings.flywheel_l3_min_history_months}mo",
        ),
    )
    return CohortStatus(
        customers_with_audit=n_audit,
        customers_with_labels=n_label,
        history_months=months,
        rungs=rungs,
    )
