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

from tokenops_cost_auditor.persistence.models import Payment, WebhookEvent
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments.base import grant_payment
from tokenops_cost_auditor.services.payments.razorpay_link import OrderWebhookEvent, WebhookPayment

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


def _credit_order(session: Session, provider: str, event: OrderWebhookEvent) -> bool:
    """Issue #74 B3: idempotent on `order_id` — a re-delivered `order.paid`,
    or `payment.captured` arriving for an order already credited by
    `order.paid` (or vice versa), is a no-op. This is IN ADDITION to the
    event-id dedup in `_record_once` (different event ids for the same order
    would otherwise slip past it)."""
    existing = session.scalar(
        select(Payment).where(Payment.provider == provider, Payment.ref == event.order_id)
    )
    if existing is not None:
        return False
    user = get_or_create_user(session, event.email)
    grant_payment(session, user.id, provider, event.amount, event.currency, ref=event.order_id)
    auditlog.append(
        session,
        f"webhook:{provider}",
        "payment.received",
        user.email,
        {"ref": event.order_id, "amount": event.amount, "currency": event.currency},
    )
    return True


def _handle_order_event(
    request: Request, provider: str, event: OrderWebhookEvent
) -> dict[str, str]:
    """Issue #74: order.paid/payment.captured (grant, idempotent by
    order_id) and payment.failed (B4: honest no-credit, never a 500 or a
    limbo response) share the SAME event-id dedup as every other webhook."""
    with request.app.state.session_factory() as session:
        if not _record_once(session, provider, event):
            session.commit()
            return {"status": "duplicate"}
        if event.kind == "failed":
            user = get_or_create_user(session, event.email)
            auditlog.append(
                session,
                f"webhook:{provider}",
                "payment.failed",
                user.email,
                {"ref": event.order_id},
            )
        else:
            _credit_order(session, provider, event)
        session.commit()
    return {"status": "processed"}


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
        # Not a payment-link payment — try the Standard Checkout order
        # lifecycle (Issue #74), then the subscription lifecycle (WP-6), all
        # on the SAME signature/tolerance/dedup rails (FR-27).
        order_event = adapter.parse_order_event(body, now_epoch=now_epoch)
        if order_event is not None:
            return _handle_order_event(request, "razorpay", order_event)
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
