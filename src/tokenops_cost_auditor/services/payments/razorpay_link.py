"""Razorpay adapter (FR-18/FR-27): env-configured payment link + webhook
verification with stdlib HMAC only (PLAN §0.2 PAYMENT-SDKS — no SDK).

Signature: X-Razorpay-Signature = HMAC-SHA256(raw_body, webhook_secret), hex.
FR-27 timestamp tolerance: Razorpay's signature carries no timestamp, so the
event payload's created_at is checked against now +/- 300s (documented choice).
Accepted event: payment_link.paid with notes.email identifying the purchaser.

Issue #74 (Standard Checkout): `order.paid` / `payment.captured` /
`payment.failed` are parsed by `parse_order_event` on the SAME signature +
FR-27 tolerance rails — these are the AUTHORITATIVE source of truth for the
one-shot credit grant (B1); the handler-payload signature check in
services/payments/razorpay_orders.py is UX-only and never itself grants.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

TOLERANCE_S = 300  # FR-27


@dataclass(frozen=True)
class WebhookPayment:
    event_id: str
    email: str
    amount: float  # major units
    currency: str
    ref: str


@dataclass(frozen=True)
class OrderWebhookEvent:
    """Issue #74 B3: `ref` on the credit ledger is keyed on `order_id` (never
    the payment/event id), so `order.paid` and `payment.captured` arriving
    for the SAME order collapse to exactly one credit."""

    event_id: str
    order_id: str
    email: str
    amount: float  # major units
    currency: str
    kind: str  # "paid" | "failed"


# order.paid and payment.captured both mean "this order is paid" — either may
# arrive first (or both), so both map to "paid" and share the order_id-keyed
# idempotent grant. payment.failed is an honest no-credit signal (B4).
RAZORPAY_ORDER_EVENTS = {
    "order.paid": "paid",
    "payment.captured": "paid",
    "payment.failed": "failed",
}

# Subscription events, normalised to the kinds subscriptions.py acts on.
RAZORPAY_SUB_EVENTS = {
    "subscription.activated": "activated",
    "subscription.charged": "renewed",
    "subscription.pending": "failed",
    "subscription.halted": "failed",
    "subscription.cancelled": "cancelled",
    "subscription.completed": "cancelled",
}


class RazorpayLinkAdapter:
    provider = "razorpay"

    def __init__(self, payment_link_url: str, webhook_secret: str) -> None:
        self._link = payment_link_url
        self._secret = webhook_secret

    def payment_link(self) -> str | None:
        return self._link or None

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not self._secret:
            return False
        expected = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def parse_event(self, body: bytes, now_epoch: int) -> WebhookPayment | None:
        """None = valid signature but not a payment we act on, stale (FR-27), or a
        payload shape we don't recognize (G5 cold-reviewer f.3 — never a 500)."""
        try:
            return self._parse(body, now_epoch)
        except ValueError, KeyError, TypeError:
            return None

    def _parse(self, body: bytes, now_epoch: int) -> WebhookPayment | None:
        data = json.loads(body)
        if data.get("event") != "payment_link.paid":
            return None
        created_at = int(data.get("created_at") or 0)
        if abs(now_epoch - created_at) > TOLERANCE_S:
            return None  # FR-27: stale event
        entity = data["payload"]["payment"]["entity"]
        email = str(entity.get("notes", {}).get("email", "")).lower()
        if not email:
            return None
        return WebhookPayment(
            event_id=str(data.get("event_id") or entity["id"]),
            email=email,
            amount=int(entity["amount"]) / 100.0,  # paise -> INR
            currency=str(entity.get("currency", "INR")),
            ref=str(entity["id"]),
        )

    def parse_order_event(self, body: bytes, now_epoch: int) -> OrderWebhookEvent | None:
        """Issue #74: order.paid / payment.captured / payment.failed, on the
        SAME FR-27 rails as payment_link.paid. None on unrecognized event
        names, stale timestamps, or a shape we don't recognize (never 500,
        matching `parse_event`'s G5 cold-reviewer f.3 rule)."""
        try:
            return self._parse_order(body, now_epoch)
        except ValueError, KeyError, TypeError:
            return None

    def _parse_order(self, body: bytes, now_epoch: int) -> OrderWebhookEvent | None:
        data = json.loads(body)
        kind = RAZORPAY_ORDER_EVENTS.get(str(data.get("event")))
        if kind is None:
            return None
        created_at = int(data.get("created_at") or 0)
        if abs(now_epoch - created_at) > TOLERANCE_S:
            return None  # FR-27: stale event
        payload = data["payload"]
        order_entity = (payload.get("order") or {}).get("entity") or {}
        payment_entity = (payload.get("payment") or {}).get("entity") or {}
        order_id = str(order_entity.get("id") or payment_entity.get("order_id") or "")
        if not order_id:
            return None
        notes = order_entity.get("notes") or payment_entity.get("notes") or {}
        email = str(notes.get("email", "")).lower()
        if not email:
            return None
        entity = payment_entity or order_entity
        return OrderWebhookEvent(
            event_id=str(data.get("event_id") or entity.get("id") or order_id),
            order_id=order_id,
            email=email,
            amount=int(entity.get("amount") or order_entity.get("amount") or 0) / 100.0,
            currency=str(entity.get("currency") or order_entity.get("currency") or "INR"),
            kind=kind,
        )

    def parse_subscription_event(self, body: bytes, now_epoch: int) -> object | None:
        """Subscription lifecycle on the SAME FR-27 rails as one-shot payments:
        caller verifies the signature first, timestamp tolerance here, dedup by
        event id downstream. Returns None for anything we do not act on."""
        from tokenops_cost_auditor.services.payments.subscriptions import SubscriptionEvent

        try:
            data = json.loads(body)
            kind = RAZORPAY_SUB_EVENTS.get(str(data.get("event")))
            if kind is None:
                return None
            created_at = int(data.get("created_at") or 0)
            if abs(now_epoch - created_at) > TOLERANCE_S:
                return None  # FR-27: stale event
            entity = data["payload"]["subscription"]["entity"]
            notes = entity.get("notes") or {}
            email = str(notes.get("email") or entity.get("customer_email") or "").lower()
            if not email:
                return None
            return SubscriptionEvent(
                event_id=str(data.get("id") or entity.get("id")),
                email=email,
                kind=kind,
                plan=str(notes.get("plan") or "pro").lower(),
                currency="INR",
                ref=str(entity.get("id") or ""),
            )
        except ValueError, KeyError, TypeError:
            return None
