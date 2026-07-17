"""Payment webhooks (FR-18/FR-27; /api/v1 per FR-25).

Order of checks per FR-27: HMAC signature -> timestamp tolerance (5 min) ->
processed-event-id dedup (append-only webhook_events; duplicates acknowledged
with 200 but never reprocessed) -> payment credit granted.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import WebhookEvent
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments.base import grant_payment
from tokenops_cost_auditor.services.payments.razorpay_link import WebhookPayment

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _record_once(session: Session, provider: str, event: WebhookPayment) -> bool:
    """FR-27 dedup: True if this event id is new; False if already processed."""
    existing = session.scalar(
        select(WebhookEvent).where(
            WebhookEvent.provider == provider, WebhookEvent.event_id == event.event_id
        )
    )
    if existing is not None:
        return False
    try:
        session.add(
            WebhookEvent(
                provider=provider,
                event_id=event.event_id,
                detail={"ref": event.ref, "amount": event.amount, "currency": event.currency},
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


@router.post("/razorpay")
async def razorpay_webhook(request: Request) -> dict[str, str]:
    adapter = request.app.state.razorpay
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not adapter.verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="invalid webhook signature")
    event = adapter.parse_event(body, now_epoch=int(time.time()))
    if event is None:
        return {"status": "ignored"}  # unhandled type or stale timestamp (FR-27)
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
        return {"status": "ignored"}
    with request.app.state.session_factory() as session:
        if not _record_once(session, "stripe", event):
            session.commit()
            return {"status": "duplicate"}
        _credit(session, "stripe", event)
        session.commit()
    return {"status": "processed"}
