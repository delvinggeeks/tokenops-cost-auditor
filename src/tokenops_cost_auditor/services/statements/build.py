"""Savings Statement (PLAN-V15 V-D6 / WP-4) — the owner artifact.

One page a month, written for whoever signs off on the bill and never logs
in here. Plain text, one column, no images, one CTA (R-DESIGN §4e).

It inherits R-Q9 law wholesale (founder, 2026-07-22):
  * the HEADLINE carries VERIFIED figures only;
  * customer-reported and identified sit in their own labelled sections;
  * every figure names the audit it came from (provenance stamps);
  * the FR-30 equiv-spend line appears whenever any audit in the period
    could not assume metered-API billing.

Month scoping and the credit rule live in savings.compute(period=...) —
one implementation of the formula, never a second copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, FindingFeedback, Statement, User, utcnow
from tokenops_cost_auditor.services.dashboard.savings import compute
from tokenops_cost_auditor.services.payments import plans, subscriptions
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE

MONTH_DAYS = 30.0


@dataclass(frozen=True)
class StatementDoc:
    period: str  # YYYY-MM
    subject: str  # the number leads (R-DESIGN §4e)
    body: str
    verified_usd: float
    identified_usd: float
    customer_reported_usd: float
    spend_usd: float
    fixes_applied: int
    equiv_spend: bool


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, next_month_start) — EXCLUSIVE at the top. A 23:59:59 upper
    bound silently dropped audits landing in the final second, so a statement
    could say "no audit ran this month" while showing a verified figure that
    came from exactly that audit (V-D6 cold-review f.2)."""
    start = datetime(year, month, 1, tzinfo=UTC)
    nxt = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )
    return start, nxt


def should_email(session: Session, settings: Settings, user: User, year: int, month: int) -> bool:
    """R-STMT-GATING (founder, 2026-07-25): who gets the monthly EMAIL.

    Archiving is unconditional for every plan — that is the caller's job and
    this function has no say in it. Pro/Scale get the email every month; Free
    only for a month with activity (an audit ran, or a finding changed state),
    because a monthly email of zeros to a dormant Free account is spam, while
    an activity statement showing identified-but-unverified savings is the
    upsell artifact.
    """
    ents = subscriptions.entitlements(session, settings, user.id)
    if str(ents["plan_key"]) in plans.PAID_PLANS:
        return True
    start, end = _month_bounds(year, month)
    audit_ran = (
        session.execute(
            select(Audit.id).where(
                Audit.user_id == user.id,
                Audit.created_at >= start,
                Audit.created_at < end,
            )
        ).first()
        is not None
    )
    if audit_ran:
        return True
    finding_changed = (
        session.execute(
            select(FindingFeedback.finding_id)
            .join(Audit, FindingFeedback.audit_id == Audit.id)
            .where(
                Audit.user_id == user.id,
                FindingFeedback.ts >= start,
                FindingFeedback.ts < end,
            )
        ).first()
        is not None
    )
    return finding_changed


def build(session: Session, user: User, year: int, month: int) -> StatementDoc:
    start, end = _month_bounds(year, month)
    audits = (
        session.execute(
            select(Audit)
            .where(
                Audit.user_id == user.id,
                Audit.status == "done",
                Audit.created_at >= start,
                Audit.created_at < end,
            )
            .order_by(Audit.created_at)
        )
        .scalars()
        .all()
    )
    summary = compute(session, user.id, period=(year, month))
    latest = audits[-1] if audits else None
    spend = 0.0
    if latest is not None:
        days = max(latest.observed_days or 1, 1)
        spend = float(latest.total_spend_usd or 0.0) * MONTH_DAYS / days
    equiv = any(bool(a.equiv_spend) for a in audits)
    period = f"{year:04d}-{month:02d}"

    subject = (
        f"${summary.verified_usd:,.2f} verified savings — {start:%B %Y} AI spend statement"
        if summary.verified_usd > 0
        else f"{start:%B %Y} AI spend statement"
    )

    lines: list[str] = [
        f"AI SPEND STATEMENT — {start:%B %Y}",
        "",
    ]
    if summary.verified_usd > 0:
        lines += [
            f"VERIFIED SAVINGS THIS MONTH: ${summary.verified_usd:,.2f}",
            "",
            f"This is money you are no longer spending. {summary.verified_count} fix(es)",
            "were applied and then re-measured against your own logs by a later",
            "audit covering at least 7 days. It is not a projection.",
        ]
    else:
        lines += [
            "VERIFIED SAVINGS THIS MONTH: none yet",
            "",
            "Nothing was confirmed this month. A saving is only called verified",
            "once a later audit re-measures the same route and proves it — we do",
            "not count a fix the moment it ships.",
        ]

    lines += ["", "WHAT YOU SPENT", ""]
    if latest is not None:
        lines += [
            f"  Run-rate at the last audit: ${spend:,.2f} per month",
            f"  Audits this month: {len(audits)}",
        ]
    else:
        lines += ["  No audit ran this month, so there is nothing to report."]

    lines += ["", "STILL ON THE TABLE (ESTIMATES, NOT SAVINGS)", ""]
    if summary.identified_usd > 0:
        lines += [
            f"  ${summary.identified_usd:,.2f} per month identified and not yet applied.",
            "  These are estimates from our detectors. They become verified figures",
            "  only after you apply a fix and a later audit confirms it.",
        ]
    elif summary.verified_count or summary.pending_count:
        # findings existed and were applied — "actioned" is true
        lines += ["  Nothing outstanding — every finding has been actioned."]
    else:
        # zero findings this month: nothing was ever there to action (readiness
        # audit — the old copy claimed "actioned" when nothing was found)
        lines += ["  No new avoidable spend was flagged this month."]

    if summary.pending_count:
        lines += [
            "",
            f"  {summary.pending_count} applied fix(es) are awaiting confirmation by the",
            "  next audit. They are deliberately absent from the figure above.",
        ]

    if summary.customer_reported_usd > 0:
        lines += [
            "",
            "REPORTED BY YOU (NOT OUR MEASUREMENT)",
            "",
            f"  ${summary.customer_reported_usd:,.2f} per month, as you recorded it.",
            "  We keep your own figures separate from ours and never add them to",
            "  the verified total.",
        ]

    if equiv:
        lines += ["", EQUIV_SPEND_LINE]

    lines += ["", "WHERE THESE NUMBERS COME FROM", ""]
    if audits:
        for a in audits:
            when = a.report_ready_at or a.created_at
            lines.append(
                f"  Audit {a.id[:4]}…{a.id[-3:]} — {when:%Y-%m-%d %H:%M} UTC, "
                f"{a.row_count or 0:,} calls over {a.observed_days or 0} day(s)"
            )
    else:
        lines.append("  No audits in this period.")

    lines += [
        "",
        "Open your dashboard to see the detail behind every figure.",
        "",
    ]

    return StatementDoc(
        period=period,
        subject=subject,
        body="\n".join(lines),
        verified_usd=summary.verified_usd,
        identified_usd=summary.identified_usd,
        customer_reported_usd=summary.customer_reported_usd,
        spend_usd=round(spend, 2),
        fixes_applied=summary.verified_count,
        equiv_spend=equiv,
    )


def archive(session: Session, user: User, doc: StatementDoc) -> Statement:
    """Store (or refresh) the statement for its period. One row per user per
    month — a re-run replaces the draft rather than stacking copies, and a
    statement already SENT is never rewritten (an archived artifact must not
    change after it has left the building)."""
    existing = session.execute(
        select(Statement).where(Statement.user_id == user.id, Statement.period == doc.period)
    ).scalar_one_or_none()
    if existing is None:
        row = Statement(user_id=user.id, period=doc.period, subject=doc.subject, body_text=doc.body)
        session.add(row)
        return row
    if existing.sent_at is None:
        existing.subject = doc.subject
        existing.body_text = doc.body
    return existing


def send(session: Session, mail: object, user: User, row: Statement) -> bool:
    """Deliver once. Returns True if this call sent it."""
    if row.sent_at is not None:
        return False
    deliver = getattr(mail, "alert", None)
    if callable(deliver):
        deliver(user.email, row.subject or f"AI spend statement {row.period}", row.body_text)
    row.sent_at = utcnow()
    return True
