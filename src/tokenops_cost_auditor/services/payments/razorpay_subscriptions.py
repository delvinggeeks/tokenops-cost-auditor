"""Razorpay Subscriptions — plan + subscription creation for recurring INR
Pro/Team (Issue #79). httpx only (PLAN §0.2 PAYMENT-SDKS — no SDK).

Verified against razorpay.com/docs/payments/subscriptions/integration-guide/:
  1. `POST /v1/plans` creates the billing plan FIRST. The amount is built
     from OUR pricing config (services/payments/plans.py Plan.inr), never a
     dashboard-entered figure — the price-integrity rail: what Razorpay
     bills can never drift from what the plans page displays.
  2. `POST /v1/subscriptions` references that plan_id. `total_count` is a
     large, ongoing bound (ADHOC_TOTAL_COUNT) — the subscription runs until
     cancelled, not for a fixed number of cycles.
  3. checkout.js opens against `subscription_id` (NOT `order_id`, unlike the
     one-time Standard Checkout flow in razorpay_orders.py).
  4. The modal handler returns {razorpay_payment_id, razorpay_subscription_id,
     razorpay_signature}. Verified here for UX/auth only (B1) — the
     `subscription.activated` webhook (razorpay_link.parse_subscription_event
     + subscriptions.apply_event, both reused unchanged from WP-6) is the
     sole activation authority.

⚠️ SIGNATURE GOTCHA: the subscription concatenation order is the OPPOSITE of
the one-time order's `order_id|payment_id` (razorpay_orders.verify_order_
signature). Subscriptions verify `payment_id|subscription_id` — payment_id
FIRST. Getting this backwards is a documented, common integration bug
(razorpay-node issue #124).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

import httpx

PLANS_URL = "https://api.razorpay.com/v1/plans"
SUBSCRIPTIONS_URL = "https://api.razorpay.com/v1/subscriptions"

# The subscription runs until cancelled (dunning ladder or customer request),
# not for a fixed term — Razorpay still requires a total_count. Razorpay CAPS
# total_count by period (monthly → 100; a larger value 4xxs every live create —
# cold-reviewer #80). 100 monthly cycles ≈ 8.3 years is our practical "ongoing"
# bound; renewal past that re-subscribes.
TOTAL_COUNT = 100  # Razorpay's max for a monthly plan


class SupportsPost(Protocol):
    """Mirrors razorpay_orders.py::SupportsPost — lets tests inject a fake
    without hitting the network."""

    def post(self, url: str, *, json: object, auth: tuple[str, str]) -> object: ...


class PlanCreateError(Exception):
    """Razorpay refused or failed the plan-create call."""


class SubscriptionCreateError(Exception):
    """Razorpay refused or failed the subscription-create call."""


def _post(
    url: str,
    payload: dict[str, object],
    key_id: str,
    key_secret: str,
    client: SupportsPost | None,
) -> object:
    if client is not None:
        return client.post(url, json=payload, auth=(key_id, key_secret))
    with httpx.Client(timeout=30.0) as http:
        return http.post(url, json=payload, auth=(key_id, key_secret))


def create_plan(
    key_id: str,
    key_secret: str,
    name: str,
    amount_rupees: float,
    client: SupportsPost | None = None,
) -> dict[str, object]:
    """POST /v1/plans. `amount` is OUR config INR charge amount in paise —
    the price-integrity rail (issue #79): the plan can never bill more or
    less than what the plans page displays for this tier."""
    amount_paise = round(amount_rupees * 100)
    payload = {
        "period": "monthly",
        "interval": 1,
        "item": {"name": name, "amount": amount_paise, "currency": "INR"},
    }
    resp = _post(PLANS_URL, payload, key_id, key_secret, client)
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        raise PlanCreateError(f"razorpay plan create failed: HTTP {status}")
    data = resp.json()  # type: ignore[attr-defined]
    plan_id = data.get("id")
    if not plan_id:
        raise PlanCreateError("razorpay plan create response carried no id")
    return {"plan_id": str(plan_id), "amount": amount_paise, "currency": "INR"}


def create_subscription(
    key_id: str,
    key_secret: str,
    plan_id: str,
    email: str,
    plan_key: str,
    client: SupportsPost | None = None,
) -> dict[str, object]:
    """POST /v1/subscriptions against an existing plan_id. `notes.plan` lets
    the subscription.activated webhook (razorpay_link.parse_subscription_
    event) know which tier to activate — without it every subscription
    defaults to "pro", silently under-granting a Team purchase."""
    payload = {
        "plan_id": plan_id,
        "total_count": TOTAL_COUNT,
        "customer_notify": 1,
        "notes": {"email": email, "plan": plan_key},
    }
    resp = _post(SUBSCRIPTIONS_URL, payload, key_id, key_secret, client)
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        raise SubscriptionCreateError(f"razorpay subscription create failed: HTTP {status}")
    data = resp.json()  # type: ignore[attr-defined]
    subscription_id = data.get("id")
    if not subscription_id:
        raise SubscriptionCreateError("razorpay subscription create response carried no id")
    return {"subscription_id": str(subscription_id)}


def verify_sub_signature(
    key_secret: str, payment_id: str, subscription_id: str, signature: str
) -> bool:
    """⚠️ payment_id FIRST — the opposite concatenation order from the
    one-time order's `order_id|payment_id` (razorpay_orders.verify_order_
    signature). A valid signature confirms the modal callback's authenticity
    only (B1); the subscription.activated webhook is the activation
    authority."""
    if not key_secret or not payment_id or not subscription_id:
        return False
    expected = hmac.new(
        key_secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")
