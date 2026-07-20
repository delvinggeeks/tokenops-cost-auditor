"""Razorpay adapter (FR-18/FR-27): env-configured payment link + webhook
verification with stdlib HMAC only (PLAN §0.2 PAYMENT-SDKS — no SDK).

Signature: X-Razorpay-Signature = HMAC-SHA256(raw_body, webhook_secret), hex.
FR-27 timestamp tolerance: Razorpay's signature carries no timestamp, so the
event payload's created_at is checked against now +/- 300s (documented choice).
Accepted event: payment_link.paid with notes.email identifying the purchaser.
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
