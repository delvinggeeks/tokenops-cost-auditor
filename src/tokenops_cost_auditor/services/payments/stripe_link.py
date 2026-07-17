"""Stripe adapter (FR-18/FR-27): env-configured payment link + webhook
verification with stdlib HMAC only (no SDK).

Stripe-Signature header: "t=<epoch>,v1=<hex>" where
v1 = HMAC-SHA256(f"{t}.{raw_body}", webhook_secret). FR-27: |now - t| <= 300s.
Accepted event: checkout.session.completed with customer_email.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from tokenops_cost_auditor.services.payments.razorpay_link import TOLERANCE_S, WebhookPayment


class StripeLinkAdapter:
    provider = "stripe"

    def __init__(self, payment_link_url: str, webhook_secret: str) -> None:
        self._link = payment_link_url
        self._secret = webhook_secret

    def payment_link(self) -> str | None:
        return self._link or None

    def verify_signature(self, body: bytes, sig_header: str, now_epoch: int) -> bool:
        if not self._secret or not sig_header:
            return False
        parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
        t, v1 = parts.get("t"), parts.get("v1")
        if not t or not v1 or not t.isdigit():
            return False
        if abs(now_epoch - int(t)) > TOLERANCE_S:  # FR-27: timestamp tolerance
            return False
        signed = f"{t}.".encode() + body
        expected = hmac.new(self._secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1)

    def parse_event(self, body: bytes) -> WebhookPayment | None:
        """None on unrecognized shapes too — a signature-valid but drifted payload
        must never 500 back to the provider (G5 cold-reviewer f.3)."""
        try:
            return self._parse(body)
        except ValueError, KeyError, TypeError:
            return None

    def _parse(self, body: bytes) -> WebhookPayment | None:
        data = json.loads(body)
        if data.get("type") != "checkout.session.completed":
            return None
        obj = data["data"]["object"]
        email = str(obj.get("customer_email") or "").lower()
        if not email:
            return None
        return WebhookPayment(
            event_id=str(data["id"]),
            email=email,
            amount=int(obj.get("amount_total") or 0) / 100.0,  # cents -> USD
            currency=str(obj.get("currency", "usd")).upper(),
            ref=str(obj["id"]),
        )
