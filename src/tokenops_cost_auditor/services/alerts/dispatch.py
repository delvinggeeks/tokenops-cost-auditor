"""Alert delivery (PLAN-V15 WP-3b): evaluate → record → email.

OBSERVE ONLY (X-02): the only side effects are an append-only AlertEvent row
and an email. Nothing here touches sources, plans or traffic.

Recording happens BEFORE sending so a mail failure cannot cause the same
alert to fire again on the next tick (at-most-once beats at-least-once when
the payload is an email to a paying customer).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import AlertEvent, User
from tokenops_cost_auditor.services.alerts.rules import Firing, evaluate
from tokenops_cost_auditor.services.payments import plans, subscriptions

log = structlog.get_logger("tokenops_cost_auditor.alerts")


def plan_watches(settings: Settings, plan_key: str) -> bool:
    """Whether anything evaluates alert rules on this plan. Alerts ride the
    scheduled-audit capability (the Pro blurb sells them together, and
    dispatch only ever runs from the schedule tick), so a plan without
    scheduled audits has no alerts — every surface that says otherwise must
    call this, so the words and the behaviour cannot drift apart (§5).

    Deliberately the plan's own capability, not the read_only-adjusted
    entitlement: dunning pauses scheduled audits and nothing else (Terms §6),
    so a past-due Pro account keeps its rules armed.
    """
    return plans.get(settings, plan_key).scheduled_audits


def watchers(session: Session, settings: Settings, users: list[User]) -> list[User]:
    """The users run_all may evaluate — plan_watches over a batch."""
    ents = subscriptions.entitlements_for(session, settings, [u.id for u in users])
    return [u for u in users if plan_watches(settings, str(ents[u.id]["plan_key"]))]


def run_for_user(
    session: Session,
    settings: Settings,
    mail: object,
    user: User,
    now: datetime | None = None,
) -> list[Firing]:
    firings = evaluate(session, settings, user, now=now)
    sent: list[Firing] = []
    for f in firings:
        session.add(
            AlertEvent(user_id=user.id, rule=f.rule, detail=f.detail, ts=now or datetime.now(UTC))
        )
        # Commit THIS event before sending, and before attempting any further
        # firing: a later failure must not roll back an email already sent
        # (V-D5 cold-review f.2 — the at-most-once claim was false when the
        # commit lived at the end of the batch).
        session.commit()
        send = getattr(mail, "alert", None)
        if callable(send):
            send(user.email, f.subject, f.body)
        log.info("alert.fired", rule=f.rule, user_id=user.id)
        sent.append(f)
    return sent


def run_all(
    session: Session, settings: Settings, mail: object, now: datetime | None = None
) -> dict[str, int]:
    """Every user whose plan watches. Failures are per-user."""
    # "watching_users", not "users": run_all only iterates plans that watch
    # (cold-review note — a count that quietly shrank under an old name
    # would mislead anyone reading the tick logs).
    stats = {"watching_users": 0, "fired": 0, "errors": 0}
    users = list(session.execute(select(User)).scalars().all())
    for user in watchers(session, settings, users):
        try:
            fired = run_for_user(session, settings, mail, user, now=now)
            stats["watching_users"] += 1
            stats["fired"] += len(fired)
        except Exception as exc:
            session.rollback()
            stats["errors"] += 1
            log.warning("alert.failed", user_id=user.id, error=str(exc)[:200])
    return stats
