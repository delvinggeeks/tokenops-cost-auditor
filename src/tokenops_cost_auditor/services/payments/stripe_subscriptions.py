"""Stripe Checkout Session (mode=subscription) for recurring USD Pro/Team
(Issue #81). httpx only (PLAN §0.2 PAYMENT-SDKS — no SDK).

Mirrors services/payments/stripe_checkout.py (the one-time USD flow), verified
against Stripe's Checkout + Billing docs:
  1. `POST /v1/checkout/sessions`, HTTP Basic Auth (secret or restricted key as
     username, empty password — identical to the one-time flow).
  2. `mode=subscription`; the line item is an INLINE `price_data` carrying
     `recurring[interval]=month` (Checkout supports inline recurring prices
     for subscription mode) — the amount is built from OUR pricing config
     (services/payments/plans.py), never a dashboard-entered figure, so the
     charge can never drift from what the plans page displays (the
     price-integrity rail).
  3. `subscription_data[metadata]` is set (not just session-level `metadata`):
     Checkout Session metadata lives on the Session object, but the
     `customer.subscription.created` webhook payload is the SUBSCRIPTION
     object — only `subscription_data[metadata]` propagates onto it. Its keys
     are `email`/`plan` (NOT `user_email`) — the exact keys the reused
     `StripeLinkAdapter.parse_subscription_event` reads off the subscription
     object's metadata (services/payments/stripe_link.py, unchanged: it was
     written for the pre-existing WP-6 webhook, and already ships in
     production reading `metadata.email`). Getting this key wrong would see
     no plan and default to "pro", silently under-granting a Team purchase.
     Session-level `metadata` additionally carries `user_email`, matching the
     one-time flow's convention (session-level metadata is not read by the
     subscription webhook path; this is for reconciliation only).
  4. The response's `url` is the hosted-checkout redirect target (303, full
     page nav — no embedded JS, no CSP change). Activation happens on the
     `customer.subscription.created` webhook (services/payments/stripe_link.py,
     services/payments/subscriptions.py — both reused, unchanged), never on
     success_url.
"""

from __future__ import annotations

from typing import Protocol

import httpx

CHECKOUT_URL = "https://api.stripe.com/v1/checkout/sessions"


class SupportsPostForm(Protocol):
    """Mirrors stripe_checkout.py::SupportsPostForm — lets tests inject a fake
    without hitting the network."""

    def post(self, url: str, *, data: object, auth: tuple[str, str]) -> object: ...


class CheckoutCreateError(Exception):
    """Stripe refused or failed the subscription session-create call."""


def create_session(
    secret_key: str,
    amount_usd: float,
    plan_name: str,
    plan_key: str,
    success_url: str,
    cancel_url: str,
    email: str,
    client: SupportsPostForm | None = None,
) -> dict[str, str]:
    """POST /v1/checkout/sessions, mode=subscription. `unit_amount` is in
    cents, built from OUR config (the price-integrity rail)."""
    amount_cents = round(amount_usd * 100)
    payload = {
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": plan_name,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": email,
        "metadata[user_email]": email,
        "metadata[plan]": plan_key,
        # Propagates onto the Subscription object itself — keys match what
        # StripeLinkAdapter.parse_subscription_event reads (see module docstring §3).
        "subscription_data[metadata][email]": email,
        "subscription_data[metadata][plan]": plan_key,
    }
    if client is not None:
        resp = client.post(CHECKOUT_URL, data=payload, auth=(secret_key, ""))
    else:
        with httpx.Client(timeout=30.0) as http:
            resp = http.post(CHECKOUT_URL, data=payload, auth=(secret_key, ""))
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        raise CheckoutCreateError(f"stripe subscription session create failed: HTTP {status}")
    data = resp.json()  # type: ignore[attr-defined]
    session_id, session_url = data.get("id"), data.get("url")
    if not session_id or not session_url:
        raise CheckoutCreateError("stripe subscription session response carried no id/url")
    return {"id": str(session_id), "url": str(session_url)}
