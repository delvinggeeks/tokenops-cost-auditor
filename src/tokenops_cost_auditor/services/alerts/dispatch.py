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

log = structlog.get_logger("tokenops_cost_auditor.alerts")


def run_for_user(
    session: Session,
    settings: Settings,
    mail: object,
    user: User,
    now: datetime | None = None,
) -> list[Firing]:
    firings = evaluate(session, settings, user, now=now)
    for f in firings:
        session.add(
            AlertEvent(user_id=user.id, rule=f.rule, detail=f.detail, ts=now or datetime.now(UTC))
        )
        session.flush()
        send = getattr(mail, "alert", None)
        if callable(send):
            send(user.email, f.subject, f.body)
        log.info("alert.fired", rule=f.rule, user_id=user.id)
    return firings


def run_all(
    session: Session, settings: Settings, mail: object, now: datetime | None = None
) -> dict[str, int]:
    """Every user with at least one enabled rule. Failures are per-user."""
    stats = {"users": 0, "fired": 0, "errors": 0}
    users = session.execute(select(User)).scalars().all()
    for user in users:
        try:
            fired = run_for_user(session, settings, mail, user, now=now)
            session.commit()
            stats["users"] += 1
            stats["fired"] += len(fired)
        except Exception as exc:
            session.rollback()
            stats["errors"] += 1
            log.warning("alert.failed", user_id=user.id, error=str(exc)[:200])
    return stats
