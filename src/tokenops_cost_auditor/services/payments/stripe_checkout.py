"""Stripe Checkout Session for the one-time USD audit (Issue #77). httpx only
(PLAN §0.2 PAYMENT-SDKS — no SDK).

Verified against Stripe's Checkout + webhooks docs (hosted redirect — the
recommended default, no embedded JS, no CSP work):
  1. The session MUST be created server-side FIRST: `POST /v1/checkout/sessions`,
     HTTP Basic Auth username=the API key, password="". The key may be a SECRET
     key (sk_test_...) or a RESTRICTED key (rk_test_...) scoped to Checkout
     Sessions (Stripe's current best-practice) — used IDENTICALLY as the
     Basic-Auth username, so this module never assumes an `sk_` prefix.
  2. The body is FORM-ENCODED (Stripe, not JSON); nested keys use bracket
     notation. `unit_amount` is in cents (USD subunits).
  3. The response's `url` is where the browser is redirected (303, full-page
     nav to checkout.stripe.com); `id` is the session id.
  4. Fulfilment happens on the `checkout.session.completed` webhook
     (services/payments/stripe_link.py, unchanged) — never on success_url.
"""

from __future__ import annotations

from typing import Protocol

import httpx

CHECKOUT_URL = "https://api.stripe.com/v1/checkout/sessions"


class SupportsPostForm(Protocol):
    """The slice of httpx.Client the session-create call uses — lets tests inject
    a fake, mirroring services/connectors/base.py::SupportsGet and
    services/payments/razorpay_orders.py::SupportsPost (form data, not json)."""

    def post(self, url: str, *, data: object, auth: tuple[str, str]) -> object: ...


class CheckoutCreateError(Exception):
    """Stripe refused or failed the session-create call."""


def create_session(
    secret_key: str,
    amount_usd: float,
    success_url: str,
    cancel_url: str,
    email: str,
    client: SupportsPostForm | None = None,
) -> dict[str, str]:
    """POST /v1/checkout/sessions. `unit_amount` is in cents per the doc."""
    amount_cents = round(amount_usd * 100)
    payload = {
        "mode": "payment",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": "One-time audit",
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": email,
        "metadata[user_email]": email,
        "metadata[purpose]": "one_shot_audit",
    }
    if client is not None:
        resp = client.post(CHECKOUT_URL, data=payload, auth=(secret_key, ""))
    else:
        with httpx.Client(timeout=30.0) as http:
            resp = http.post(CHECKOUT_URL, data=payload, auth=(secret_key, ""))
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        raise CheckoutCreateError(f"stripe checkout session create failed: HTTP {status}")
    data = resp.json()  # type: ignore[attr-defined]
    session_id, session_url = data.get("id"), data.get("url")
    if not session_id or not session_url:
        raise CheckoutCreateError("stripe checkout session response carried no id/url")
    return {"id": str(session_id), "url": str(session_url)}
