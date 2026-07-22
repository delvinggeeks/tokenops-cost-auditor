"""R-DAILY-LOOP (founder-ratified 2026-07-22): the daily surface.

The data already lands daily (scheduled pulls); this module is the surface
that makes the product a morning habit: one email a day per paying customer
with yesterday's spend per source, the delta against their own 7-day
average, month-to-date, and — when they set a budget on /alerts — staged
50/80/100% budget progress through the existing alert machinery.

House rules carried over verbatim:
- R-STMT-GATING grammar: emailed only when there is something to show — a
  zero-spend day stamps and stays silent.
- R-DESIGN §4e: the subject carries the number.
- Spend is computed with the SAME rate math as source audits (uncached
  input + cache reads + output against the verified rate card) so the
  digest, the dashboard tile and the audit never disagree about a number.
- OBSERVE ONLY (X-02): budget staging records an AlertEvent and emails.
  Nothing here touches sources, plans or traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import cast

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    AlertRule,
    Source,
    SourceUsage,
    User,
)
from tokenops_cost_auditor.services.alerts.rules import SOFT_BUDGET
from tokenops_cost_auditor.services.payments import plans, subscriptions
from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable

log = structlog.get_logger("tokenops_cost_auditor.daily")

BUDGET_STAGES = (100, 80, 50)  # checked high-to-low; the highest crossed fires


@dataclass
class DaySpend:
    total_usd: float = 0.0
    by_source: dict[str, float] = field(default_factory=dict)  # label -> usd
    unpriced: set[str] = field(default_factory=set)


def _rate_cost(table: PricingTable, provider: str, row: SourceUsage) -> float | None:
    """The audit's own per-bucket math (source_audit.py) — one formula,
    every surface."""
    try:
        rate = table.rate(provider, row.model, cast(date, row.day))
    except PricingGapError:
        return None
    uncached = max(0, row.prompt_tokens - row.cached_tokens)
    return (
        uncached * rate.input
        + row.cached_tokens * rate.cache_read
        + row.completion_tokens * rate.output
    ) / 1e6


def spend_between(
    session: Session, table: PricingTable, user_id: str, first: date, last: date
) -> DaySpend:
    """Priced spend for one user's sources over [first, last] inclusive."""
    rows = session.execute(
        select(SourceUsage, Source)
        .join(Source, SourceUsage.source_id == Source.id)
        .where(Source.user_id == user_id, SourceUsage.day >= first, SourceUsage.day <= last)
    ).all()
    out = DaySpend()
    for usage, source in rows:
        cost = _rate_cost(table, source.provider, usage)
        if cost is None:
            out.unpriced.add(usage.model)
            continue
        out.total_usd += cost
        out.by_source[source.label] = out.by_source.get(source.label, 0.0) + cost
    return out


def _budget_stage_crossed(
    session: Session, user: User, rule: AlertRule, mtd_usd: float, now: datetime
) -> int | None:
    """The highest 50/80/100 stage newly crossed this month, or None.
    Dedupe rides AlertEvent rows: a stage fires once per calendar month."""
    if not rule.enabled or not rule.threshold or float(rule.threshold) <= 0:
        return None
    pct = mtd_usd / float(rule.threshold) * 100.0
    crossed = next((s for s in BUDGET_STAGES if pct >= s), None)
    if crossed is None:
        return None
    month = f"{now:%Y-%m}"
    # bounded to the month in SQL — the per-user scan must not grow with
    # account age (cold-review f.3); the detail month check stays as the
    # authoritative filter
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    fired = session.execute(
        select(AlertEvent).where(
            AlertEvent.user_id == user.id,
            AlertEvent.rule == SOFT_BUDGET,
            AlertEvent.ts >= month_start,
        )
    ).scalars()
    best = max(
        (
            int(e.detail.get("stage", 0))
            for e in fired
            if isinstance(e.detail, dict) and e.detail.get("month") == month
        ),
        default=0,
    )
    return crossed if crossed > best else None


def _fmt(amount: float) -> str:
    return f"${amount:,.2f}"


def _inr_line(settings: Settings, currency: str, usd: float) -> str:
    if currency != "INR" or usd <= 0:
        return ""
    inr = usd * settings.inr_per_usd_display
    return f" (≈₹{inr:,.0f} at ₹{settings.inr_per_usd_display:,.0f}/$)"


def run_digests(
    session: Session,
    settings: Settings,
    table: PricingTable,
    mail: object,
    now: datetime | None = None,
) -> dict[str, int]:
    """One pass, at most one email per paying customer per UTC day."""
    now = now or datetime.now(UTC)
    today = now.date()
    yesterday = today - timedelta(days=1)
    stats = {"digests_sent": 0, "digests_skipped": 0, "digest_errors": 0, "budget_stages": 0}
    users = list(session.execute(select(User)).scalars().all())
    ents = subscriptions.entitlements_for(session, settings, [u.id for u in users])
    send = getattr(mail, "alert", None)
    for user in users:
        try:
            plan_key = str(ents[user.id]["plan_key"])
            if plan_key not in plans.PAID_PLANS:
                continue  # the daily loop is a paid-plan surface (R-DAILY-LOOP)
            last = user.last_daily_digest_at
            if last is not None:
                last = last if last.tzinfo else last.replace(tzinfo=UTC)
                if last.date() >= today:
                    continue  # already went out today
            day = spend_between(session, table, user.id, yesterday, yesterday)
            week = spend_between(
                session,
                table,
                user.id,
                yesterday - timedelta(days=7),
                yesterday - timedelta(days=1),
            )
            mtd = spend_between(session, table, user.id, today.replace(day=1), yesterday)
            budget_rule = session.execute(
                select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.rule == SOFT_BUDGET)
            ).scalar_one_or_none()
            stage = (
                _budget_stage_crossed(session, user, budget_rule, mtd.total_usd, now)
                if budget_rule is not None
                else None
            )
            if day.total_usd <= 0 and stage is None:
                # R-STMT-GATING grammar: nothing to show, nothing sent
                user.last_daily_digest_at = now
                session.commit()
                stats["digests_skipped"] += 1
                continue

            currency = plans.viewer_currency(session, user.id, None)
            avg = week.total_usd / 7.0
            delta = ""
            if avg > 0:
                pct = (day.total_usd - avg) / avg * 100.0
                delta = f" ({'+' if pct >= 0 else ''}{pct:,.0f}% vs your 7-day average)"
            lines = [
                f"Yesterday ({yesterday:%d %b}): {_fmt(day.total_usd)}"
                f"{_inr_line(settings, currency, day.total_usd)}{delta}"
            ]
            for label, usd in sorted(day.by_source.items(), key=lambda kv: -kv[1]):
                lines.append(f"  · {label}: {_fmt(usd)}")
            lines.append(
                f"Month so far: {_fmt(mtd.total_usd)}{_inr_line(settings, currency, mtd.total_usd)}"
            )
            if budget_rule is not None and budget_rule.enabled and budget_rule.threshold:
                pct = mtd.total_usd / float(budget_rule.threshold) * 100.0
                budget_amount = _fmt(float(budget_rule.threshold))
                lines.append(f"Budget: {pct:,.0f}% of your {budget_amount}/mo line used.")
            if day.unpriced:
                lines.append(
                    "Some models had no verified rate and are excluded: "
                    + ", ".join(sorted(day.unpriced))
                )
            base = settings.app_base_url or "https://tokenops-cost-auditor.com"
            lines.append(f"\nDashboard: {base}/dashboard")

            if stage is not None:
                # record BEFORE sending (at-most-once, the alerts law)
                session.add(
                    AlertEvent(
                        user_id=user.id,
                        rule=SOFT_BUDGET,
                        detail={
                            "stage": stage,
                            "month": f"{now:%Y-%m}",
                            "mtd_usd": round(mtd.total_usd, 2),
                            "budget_usd": float(budget_rule.threshold),
                        },
                        ts=now,
                    )
                )
                stats["budget_stages"] += 1
            user.last_daily_digest_at = now
            session.commit()

            if stage == 100:
                subject = f"Over budget: {_fmt(mtd.total_usd)} this month — TokenOps daily"
            elif stage is not None:
                subject = (
                    f"{stage}% of budget used — {_fmt(day.total_usd)} yesterday — TokenOps daily"
                )
            else:
                subject = f"{_fmt(day.total_usd)} yesterday — TokenOps daily"
            if callable(send):
                send(user.email, subject, "\n".join(lines))
                stats["digests_sent"] += 1
                log.info("digest.sent", user_id=user.id, total=round(day.total_usd, 4))
            else:
                # a mail object without .alert must be loud, not a silent
                # "sent" in the stats (cold-review f.1)
                stats["digest_errors"] += 1
                log.warning("digest.mail_unusable", user_id=user.id)
        except Exception as exc:
            session.rollback()
            stats["digest_errors"] += 1
            log.warning("digest.failed", user_id=user.id, error=str(exc)[:200])
    return stats
