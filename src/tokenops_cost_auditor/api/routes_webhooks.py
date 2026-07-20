"""Payment webhooks (FR-18/FR-27; /api/v1 per FR-25).

Order of checks per FR-27: HMAC signature -> timestamp tolerance (5 min) ->
processed-event-id dedup (append-only webhook_events; duplicates acknowledged
with 200 but never reprocessed) -> payment credit granted.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import WebhookEvent
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments.base import grant_payment
from tokenops_cost_auditor.services.payments.razorpay_link import WebhookPayment

if TYPE_CHECKING:
    from tokenops_cost_auditor.services.payments.subscriptions import SubscriptionEvent

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class HasEventId(Protocol):
    """Both one-shot payments and subscription events carry an id; that is
    all the dedup rail needs to know about them. Read-only, because both
    concrete types are frozen dataclasses."""

    @property
    def event_id(self) -> str: ...


def _record_once(session: Session, provider: str, event: HasEventId) -> bool:
    """FR-27 dedup: True if this event id is new; False if already processed.

    Shared by one-shot payments and subscription events, which carry
    different fields — the detail blob records whatever the event has rather
    than assuming a payment shape.
    """
    existing = session.scalar(
        select(WebhookEvent).where(
            WebhookEvent.provider == provider,
            WebhookEvent.event_id == event.event_id,
        )
    )
    if existing is not None:
        return False
    try:
        session.add(
            WebhookEvent(
                provider=provider,
                event_id=event.event_id,
                detail={
                    "ref": getattr(event, "ref", ""),
                    "amount": getattr(event, "amount", None),
                    "currency": getattr(event, "currency", ""),
                    "kind": getattr(event, "kind", "payment"),
                },
            )
        )
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    return True


def _credit(session: Session, provider: str, event: WebhookPayment) -> None:
    user = get_or_create_user(session, event.email)
    grant_payment(session, user.id, provider, event.amount, event.currency, ref=event.ref)
    auditlog.append(
        session,
        f"webhook:{provider}",
        "payment.received",
        user.email,
        {"ref": event.ref, "amount": event.amount, "currency": event.currency},
    )


def _handle_subscription(
    request: Request, provider: str, event: SubscriptionEvent
) -> dict[str, str]:
    """Subscription events share the one-shot dedup table: an event id is
    processed at most once, whatever it was about (FR-27)."""
    from tokenops_cost_auditor.services.payments import subscriptions

    with request.app.state.session_factory() as session:
        if not _record_once(session, provider, event):
            session.commit()
            return {"status": "duplicate"}
        subscriptions.apply_event(
            session,
            request.app.state.settings,
            provider,
            event,
            mail=request.app.state.mail,
        )
        session.commit()
    return {"status": "processed"}


@router.post("/razorpay")
async def razorpay_webhook(request: Request) -> dict[str, str]:
    adapter = request.app.state.razorpay
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not adapter.verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="invalid webhook signature")
    now_epoch = int(time.time())
    event = adapter.parse_event(body, now_epoch=now_epoch)
    if event is None:
        # Not a one-shot payment — try the subscription lifecycle (WP-6), on
        # the SAME signature/tolerance/dedup rails (FR-27).
        sub_event = adapter.parse_subscription_event(body, now_epoch=now_epoch)
        if sub_event is None:
            return {"status": "ignored"}  # unhandled type or stale timestamp
        return _handle_subscription(request, "razorpay", sub_event)
    with request.app.state.session_factory() as session:
        if not _record_once(session, "razorpay", event):
            session.commit()
            return {"status": "duplicate"}  # acknowledged, not reprocessed
        _credit(session, "razorpay", event)
        session.commit()
    return {"status": "processed"}


@router.post("/stripe")
async def stripe_webhook(request: Request) -> dict[str, str]:
    adapter = request.app.state.stripe
    body = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    if not adapter.verify_signature(body, sig_header, now_epoch=int(time.time())):
        raise HTTPException(status_code=400, detail="invalid webhook signature")
    event = adapter.parse_event(body)
    if event is None:
        sub_event = adapter.parse_subscription_event(body)
        if sub_event is None:
            return {"status": "ignored"}
        return _handle_subscription(request, "stripe", sub_event)
    with request.app.state.session_factory() as session:
        if not _record_once(session, "stripe", event):
            session.commit()
            return {"status": "duplicate"}
        _credit(session, "stripe", event)
        session.commit()
    return {"status": "processed"}
