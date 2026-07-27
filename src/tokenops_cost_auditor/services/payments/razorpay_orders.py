"""Razorpay Standard Checkout — order creation + handler-payload signature
verification (Issue #74). httpx only (PLAN §0.2 PAYMENT-SDKS — no SDK).

Verified against Razorpay's Standard Web Integration doc:
  1. The order MUST be created server-side FIRST: `POST /v1/orders`, HTTP
     Basic Auth (key_id:key_secret), amount in SUBUNITS (INR paise =
     rupees*100). A payment with no order_id is auto-refunded, so this call
     is not optional.
  2. The checkout.js modal opens against that order_id (client-side).
  3. The modal `handler` callback returns {razorpay_order_id,
     razorpay_payment_id, razorpay_signature}; the signature is
     HMAC-SHA256("{order_id}|{payment_id}", key_secret) hex — verified here.
     A valid signature confirms the response is authentic (UX only, B1 —
     the order.paid webhook in razorpay_link.py is the credit-grant
     authority).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

import httpx

ORDERS_URL = "https://api.razorpay.com/v1/orders"


class SupportsPost(Protocol):
    """The slice of httpx.Client the order-create call uses — lets tests
    inject a fake, mirroring services/connectors/base.py::SupportsGet."""

    def post(self, url: str, *, json: object, auth: tuple[str, str]) -> object: ...


class OrderCreateError(Exception):
    """Razorpay refused or failed the order-create call."""


def create_order(
    key_id: str,
    key_secret: str,
    amount_rupees: float,
    receipt: str,
    email: str,
    client: SupportsPost | None = None,
) -> dict[str, object]:
    """POST /v1/orders. `amount` is in paise (INR subunits) per the doc."""
    amount_paise = round(amount_rupees * 100)
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        # Razorpay caps `receipt` at 40 chars; a longer value 400s the live API
        # (cold-reviewer #75). Callers send a short receipt — clamp as a safety net so
        # no future caller can silently break a real order on this formatting detail.
        "receipt": receipt[:40],
        "notes": {"email": email},
    }
    if client is not None:
        resp = client.post(ORDERS_URL, json=payload, auth=(key_id, key_secret))
    else:
        with httpx.Client(timeout=30.0) as http:
            resp = http.post(ORDERS_URL, json=payload, auth=(key_id, key_secret))
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        raise OrderCreateError(f"razorpay order create failed: HTTP {status}")
    data = resp.json()  # type: ignore[attr-defined]
    order_id = data.get("id")
    if not order_id:
        raise OrderCreateError("razorpay order create response carried no id")
    return {"order_id": str(order_id), "amount": amount_paise, "currency": "INR"}


def verify_order_signature(key_secret: str, order_id: str, payment_id: str, signature: str) -> bool:
    if not key_secret or not order_id or not payment_id:
        return False
    expected = hmac.new(
        key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")
