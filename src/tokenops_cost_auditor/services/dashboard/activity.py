"""Activity feed (Wave B — retention). A unified, typed timeline built from
tables that already exist — audits completed, alerts fired, verified savings,
payments — so a returning customer sees WHAT CHANGED since they last looked.
No new event table; the feed is a query, and `unseen` counts events after
users.activity_seen_at (the topbar bell badge).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    Audit,
    FindingFeedback,
    Payment,
    User,
)
from tokenops_cost_auditor.persistence.repo import active_workspace_id
from tokenops_cost_auditor.services.alerts.rules import RULE_LABELS


@dataclass(frozen=True)
class Event:
    ts: datetime
    kind: str  # audit | alert | saving | payment
    icon: str  # sprite id
    title: str
    detail: str
    href: str


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def recent(session: Session, user_id: str, limit: int = 25) -> list[Event]:
    # O-1b read-scope: audits, applied-fix feedback and alert events are all
    # workspace-owned, so the feed shows the active WORKSPACE's activity to its
    # members. Payment STAYS user-scoped — billing visibility is role-gated in
    # O-2 (founder ruling), so a plain member never sees the workspace's
    # payments here; a member's own (empty) payment line is the honest result.
    ws = active_workspace_id(session, user_id)
    events: list[Event] = []

    audits = (
        session.execute(
            select(Audit)
            .where(
                Audit.workspace_id == ws,
                Audit.status == "done",
                Audit.report_ready_at.is_not(None),
            )
            .order_by(Audit.report_ready_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for a in audits:
        savings = f" · ${a.total_spend_usd:,.0f}/mo run-rate" if a.total_spend_usd else ""
        events.append(
            Event(
                ts=_aware(a.report_ready_at or a.created_at),
                kind="audit",
                icon="i-detector",
                title="Audit completed",
                detail=f"{a.row_count or 0:,} calls analyzed{savings}",
                href="/findings",  # the in-app, session-authed view of what it found
            )
        )

    alerts = (
        session.execute(
            select(AlertEvent)
            .where(AlertEvent.workspace_id == ws)
            .order_by(AlertEvent.ts.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for e in alerts:
        events.append(
            Event(
                ts=_aware(e.ts),
                kind="alert",
                icon="i-alert",
                title=RULE_LABELS.get(e.rule, "Alert"),
                detail="Watched between audits — a notification, nothing paused.",
                href="/alerts",
            )
        )

    # Applied fixes — an HONEST event: a fix was applied, and its saving is
    # verified on the NEXT audit (never claimed verified here). ux-gate FAIL:
    # savings_realized_usd is a SELF-REPORTED figure (savings.py keeps it as
    # customer_reported, "never in the headline"); labeling it "verified" was
    # the exact false-claim the honesty laws forbid. The genuinely-verified
    # total lives on the savings widget (savings.compute().verified_usd).
    applied = (
        session.execute(
            select(FindingFeedback)
            .join(Audit, FindingFeedback.audit_id == Audit.id)
            .where(Audit.workspace_id == ws, FindingFeedback.verdict == "applied")
            .order_by(FindingFeedback.ts.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for fb in applied:
        events.append(
            Event(
                ts=_aware(fb.ts),
                kind="applied",
                icon="i-check",
                title="Fix applied",
                detail="Your next audit re-measures this route; any confirmed "
                "saving joins your verified headline.",
                href="/findings",
            )
        )

    payments = (
        session.execute(
            select(Payment)
            .where(Payment.user_id == user_id, Payment.provider != "comp")
            .order_by(Payment.ts.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    for p in payments:
        events.append(
            Event(
                ts=_aware(p.ts),
                kind="payment",
                icon="i-billing",
                title="Payment received",
                detail=f"{p.currency} {p.amount:,.0f}",
                href="/billing",
            )
        )

    events.sort(key=lambda e: e.ts, reverse=True)
    return events[:limit]


def unseen_count(session: Session, user: User, limit: int = 25) -> int:
    """How many recent events landed after the customer last opened the feed.
    Lightweight COUNTs (ux-gate perf note), not a full recent() materialize —
    the topbar bell only needs the number, capped at `limit`."""
    from sqlalchemy import func

    cut = _aware(user.activity_seen_at) if user.activity_seen_at is not None else None
    # O-1b: mirror recent()'s scoping EXACTLY or the bell badge would over/under-
    # count — audits + applied feedback + alert events are workspace-scoped;
    # Payment stays user-scoped (billing visibility is O-2).
    ws = active_workspace_id(session, user.id)

    def c(stmt: Select[tuple[int]]) -> int:
        return int(session.execute(stmt).scalar_one())

    aq = select(func.count(Audit.id)).where(
        Audit.workspace_id == ws, Audit.status == "done", Audit.report_ready_at.is_not(None)
    )
    eq = select(func.count(AlertEvent.id)).where(AlertEvent.workspace_id == ws)
    fq = (
        select(func.count(FindingFeedback.id))
        .join(Audit, FindingFeedback.audit_id == Audit.id)
        .where(Audit.workspace_id == ws, FindingFeedback.verdict == "applied")
    )
    pq = select(func.count(Payment.id)).where(
        Payment.user_id == user.id, Payment.provider != "comp"
    )
    if cut is not None:
        aq = aq.where(Audit.report_ready_at > cut)
        eq = eq.where(AlertEvent.ts > cut)
        fq = fq.where(FindingFeedback.ts > cut)
        pq = pq.where(Payment.ts > cut)
    return min(c(aq) + c(eq) + c(fq) + c(pq), limit)
