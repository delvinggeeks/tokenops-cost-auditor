"""Subscription lifecycle + dunning ladder (PLAN-V15 V-D8 / WP-6).

R-Q11/Q12, implemented exactly:

    day 0   payment fails  -> status past_due, email the customer, the
                              provider's own smart retries continue
    day 7   still failing  -> status read_only: the dashboard stays visible,
                              SCHEDULED audits pause, connections are KEPT
    day 21  still failing  -> cancelled, account reverts to Free

Data lifecycle is untouched by any of this: cancellation never triggers a
deletion beyond the normal purge rules (founder ruling, verbatim).

The ladder is a PURE function of (failed_at, now) so it can be tested
without clocks or webhooks, and the sweep that applies it is idempotent —
re-running it never double-emails or skips a rung.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Subscription, User, utcnow
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans

log = structlog.get_logger("tokenops_cost_auditor.subscriptions")

ACTIVE = "active"
PAST_DUE = "past_due"
READ_ONLY = "read_only"
CANCELLED = "cancelled"

# Webhook event kinds we act on, normalised across providers.
ACTIVATED = "activated"
RENEWED = "renewed"
FAILED = "failed"
CANCELLED_EVENT = "cancelled"


@dataclass(frozen=True)
class SubscriptionEvent:
    event_id: str
    email: str
    kind: str  # activated | renewed | failed | cancelled
    plan: str  # free | pro | team
    currency: str
    ref: str


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def dunning_stage(failed_at: datetime | None, now: datetime, settings: Settings) -> str | None:
    """The rung this subscription has reached. None = not in dunning."""
    if failed_at is None:
        return None
    days = (now - _aware(failed_at)).days
    if days >= settings.dunning_cancel_days:  # 21
        return CANCELLED
    if days >= settings.dunning_readonly_days:  # 7
        return READ_ONLY
    return PAST_DUE


def entitlements(session: Session, settings: Settings, user_id: str) -> dict[str, object]:
    """What this account may do right now. Read-only pauses SCHEDULED work
    and nothing else — the dashboard stays visible and connections are kept."""
    sub = session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    ).scalar_one_or_none()
    status = sub.status if sub else ACTIVE
    plan_key = sub.plan if sub and status != CANCELLED else plans.FREE
    plan = plans.get(settings, plan_key)
    read_only = status == READ_ONLY
    return {
        "plan": plan,
        "plan_key": plan.key,
        "status": status,
        "read_only": read_only,
        "sources_allowed": plan.sources,
        # the one thing read-only actually stops
        "scheduled_audits": plan.scheduled_audits and not read_only,
        "dashboard_visible": True,
        "connections_kept": True,
    }


def apply_event(
    session: Session, settings: Settings, provider: str, event: SubscriptionEvent
) -> Subscription:
    """Move the subscription per a verified, deduplicated webhook event."""
    user = session.execute(select(User).where(User.email == event.email)).scalar_one_or_none()
    if user is None:
        user = User(email=event.email.lower())
        session.add(user)
        session.flush()
    sub = session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user.id, provider=provider, plan=plans.FREE)
        session.add(sub)
        session.flush()

    sub.provider = provider
    sub.currency = event.currency.upper()
    sub.external_ref = event.ref
    sub.updated_at = utcnow()

    if event.kind in (ACTIVATED, RENEWED):
        sub.plan = event.plan
        sub.status = ACTIVE
        sub.failed_at = None  # a successful charge clears the dunning clock
    elif event.kind == FAILED:
        # Only START the clock; a second failure must not restart it, or the
        # ladder would never reach day 7.
        if sub.failed_at is None:
            sub.failed_at = utcnow()
        sub.status = PAST_DUE
    elif event.kind == CANCELLED_EVENT:
        sub.status = CANCELLED
        sub.plan = plans.FREE
        sub.failed_at = None
    auditlog.append(
        session,
        user.email,
        f"subscription.{event.kind}",
        user.email,
        {"provider": provider, "plan": sub.plan, "status": sub.status},
    )
    log.info("subscription.event", kind=event.kind, provider=provider, plan=sub.plan)
    return sub


def advance_dunning(
    session: Session, settings: Settings, mail: object, now: datetime | None = None
) -> dict[str, int]:
    """Walk every failing subscription to the rung it has reached.

    Idempotent: a rung is applied only when the status is not already there,
    so re-running the sweep sends no second email and skips no rung.
    """
    now = now or datetime.now(UTC)
    stats = {"past_due": 0, "read_only": 0, "cancelled": 0}
    subs = (
        session.execute(select(Subscription).where(Subscription.failed_at.is_not(None)))
        .scalars()
        .all()
    )
    for sub in subs:
        stage = dunning_stage(sub.failed_at, now, settings)
        if stage is None or stage == sub.status:
            continue
        user = session.get(User, sub.user_id)
        if user is None:
            continue
        previous = sub.status
        sub.status = stage
        sub.updated_at = utcnow()
        if stage == CANCELLED:
            sub.plan = plans.FREE
            sub.failed_at = None  # the ladder is finished
        stats[stage] = stats.get(stage, 0) + 1
        _notify(mail, user.email, stage, settings)
        auditlog.append(
            session,
            "system@dunning",
            f"subscription.{stage}",
            user.email,
            {"from": previous},
        )
        log.info("subscription.dunning", stage=stage, user_id=user.id)
    session.commit()
    return stats


def _notify(mail: object, email: str, stage: str, settings: Settings) -> None:
    """Plain words, one action, no threats. The customer is not a suspect."""
    bodies = {
        PAST_DUE: (
            "We couldn't take this month's payment",
            "Your card was declined, so this month's payment hasn't gone through.\n\n"
            "Your account is working normally and your provider will retry "
            "automatically. Updating your card in Billing fixes it immediately.\n\n"
            f"If it is still failing in {settings.dunning_readonly_days} days, "
            "scheduled audits pause — your data and connections stay put.",
        ),
        READ_ONLY: (
            "Scheduled audits are paused while payment is outstanding",
            "We still haven't been able to take payment, so scheduled audits are "
            "paused for now.\n\n"
            "Everything you already have stays exactly where it is: your reports, "
            "your dashboard, your connected sources. Update your card in Billing "
            "and the schedule resumes.",
        ),
        CANCELLED: (
            "Your subscription has ended — your account is on Free",
            "After several weeks we still couldn't take payment, so the "
            "subscription has ended and your account is back on the Free plan.\n\n"
            "Nothing has been deleted. Your reports and statements remain "
            "readable, and your data follows the same retention policy as "
            "always. You can subscribe again whenever you like.",
        ),
    }
    subject, body = bodies[stage]
    send = getattr(mail, "alert", None)
    if callable(send):
        send(email, subject, body)
