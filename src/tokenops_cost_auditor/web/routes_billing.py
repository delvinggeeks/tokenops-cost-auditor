"""Billing (PLAN-V15 V-D8 / WP-6).

Shows the plan, what it costs in BOTH currencies (R-Q11), and the state of
any outstanding payment in plain words. No card is ever collected for Free.

Subscription checkout is a provider-hosted link — we never see card details.
The one-shot INR audit (Issue #74) uses Razorpay Standard Checkout instead:
an order is created server-side (`POST /razorpay/order`), the client opens
the checkout.js modal against it, and the modal's signed callback is checked
server-side (`POST /razorpay/verify`) for UX only — the `order.paid` webhook
(api/routes_webhooks.py) is what actually grants the credit (B1).

The one-shot USD audit (Issue #77) mirrors this with a Stripe Checkout
Session instead of the old static payment link: `POST /stripe/checkout`
creates the session server-side then 303-redirects the browser straight to
Stripe's hosted page (no iframe, no client JS). Fulfilment happens on the
`checkout.session.completed` webhook (api/routes_webhooks.py, unchanged) —
never on the success_url redirect, since a user can reach that URL without
paying.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.repo import active_role, get_or_create_user
from tokenops_cost_auditor.services.geo import resolver as geo
from tokenops_cost_auditor.services.payments import (
    plans,
    razorpay_orders,
    stripe_checkout,
    subscriptions,
)
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

router = APIRouter(prefix="/billing", tags=["billing"])

# Issue #74: the modal is an iframe served from checkout.razorpay.com and it
# calls back to api.razorpay.com — without these the modal cannot load. Set
# only on the billing page (the one surface that opens it), not app-wide.
RAZORPAY_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com; "
    "frame-src 'self' https://checkout.razorpay.com; "
    "connect-src 'self' https://api.razorpay.com https://checkout.razorpay.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'"
)

STATUS_WORDS = {
    subscriptions.ACTIVE: "Everything is up to date.",
    subscriptions.PAST_DUE: (
        "We couldn't take your last payment. Your account works normally while "
        "your provider retries — updating your card fixes it immediately."
    ),
    subscriptions.READ_ONLY: (
        "Scheduled audits are paused while payment is outstanding. Your reports, "
        "dashboard and connected sources are all still here."
    ),
    subscriptions.CANCELLED: (
        "Your subscription ended and the account is on Free. Nothing was deleted."
    ),
}


@router.get("", response_class=HTMLResponse)
def billing_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ent = subscriptions.entitlements(session, settings, user.id)
        catalogue = plans.catalogue(settings)
        current = ent["plan"]
        status = str(ent["status"])
        ccy_param = request.query_params.get("ccy")
        # R-PRICING-FINAL-2 / Issue #70: a subscribed account is LOCKED to its
        # own billing currency (honesty rail — no live-looking toggle for
        # them); everyone else gets the viewer pick (toggle honoured).
        locked = plans.locked_currency(session, user.id)
        currency = locked or plans.pick_currency(
            ccy_param,
            geo.country_for_request(request, settings),
            request.cookies.get("ccy"),
        )
        launch = plans.launch_open(session, settings, currency)
        # Issue #77: honest post-redirect state. Never grants anything here — the
        # checkout.session.completed webhook is the sole authority; a user can
        # reach success_url without having actually paid.
        checkout_status = request.query_params.get("checkout")
        checkout_message = {
            "success": (
                "Payment received — your credit lands as soon as Stripe confirms "
                "it. Refresh to see it."
            ),
            "cancelled": "Checkout cancelled — nothing was charged.",
        }.get(checkout_status or "", "")
        ctx = _shell_ctx(session, request, user, "billing")
        response = _render(
            request,
            "app/billing.html",
            catalogue=[catalogue[k] for k in plans.ALL_PLANS],
            current=current,
            status=status,
            status_words=STATUS_WORDS.get(status, ""),
            read_only=bool(ent["read_only"]),
            currency=currency,
            currency_locked=locked is not None,
            launch_open=launch,
            cohort_size=settings.launch_cohort_size,
            one_shot=plans.one_shot_display(settings, currency),
            one_shot_billed=plans.one_shot_billed_note(settings, currency),
            # per-plan checkout: each paid plan carries ITS OWN link, so the
            # tier the customer picks is the tier they pay for (readiness audit)
            checkout_links={k: settings.checkout_link(currency, k) for k in plans.PAID_PLANS},
            # Issue #74: Razorpay Standard Checkout for the one-shot INR audit
            # — honest disabled state when the test key isn't configured.
            razorpay_configured=bool(settings.razorpay_key_id and settings.razorpay_key_secret),
            # Issue #77: Stripe Checkout Session for the one-shot USD audit —
            # honest disabled state when the API key isn't configured.
            stripe_configured=bool(settings.stripe_secret_key),
            checkout_status=checkout_status,
            checkout_message=checkout_message,
            now=datetime.now(UTC),
            show_tour=False,
            # ctx's plan feeds the topbar badge; billing.html itself reads
            # `current`, so there is no collision — excluding plan rendered
            # an empty badge (seen on the page, not in review).
            **ctx,
        )
        if locked is None and ccy_param and currency != request.cookies.get("ccy"):
            # an explicit toggle choice persists across pages and visits — the
            # same behaviour /pricing and / already give an unsubscribed
            # viewer (Issue #70: billing was the one surface missing it).
            response.set_cookie(
                "ccy", currency, max_age=365 * 86400, httponly=False, samesite="lax"
            )
        response.headers["Content-Security-Policy"] = RAZORPAY_CSP
        return response


@router.post("/razorpay/order")
def create_razorpay_order(
    request: Request, user_email: str = Depends(current_user)
) -> JSONResponse:
    """Issue #74 step 1: create the Razorpay order server-side BEFORE the
    checkout modal opens — a payment with no order_id auto-refunds."""
    settings = request.app.state.settings
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise HTTPException(status_code=503, detail="checkout not switched on")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: billing is an owner-only action, same gate as the plan table.
        # Authorize BEFORE committing, so a non-owner attempt leaves no orphan user
        # row — the flushed user rolls back when the session closes (cold-reviewer #75).
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_BILLING,
            detail="only the workspace owner can buy an audit",
        )
        session.commit()
        user_id = user.id
    try:
        order = razorpay_orders.create_order(
            settings.razorpay_key_id,
            settings.razorpay_key_secret,
            settings.one_shot_inr,
            # Razorpay caps `receipt` at 40 chars — the old oneshot-{user_id:32}-{uuid}
            # form was 53 and would 400 every live order (cold-reviewer #75). Keep it
            # short + unique; notes.email carries identity for reconciliation.
            receipt=f"1x-{user_id[:8]}-{uuid4().hex[:12]}",
            email=user_email,
        )
    except razorpay_orders.OrderCreateError as exc:
        raise HTTPException(status_code=502, detail="payment provider error") from exc
    return JSONResponse(
        {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": settings.razorpay_key_id,
        }
    )


@router.post("/razorpay/verify")
def verify_razorpay_payment(
    request: Request,
    razorpay_order_id: str = Form(...),
    razorpay_payment_id: str = Form(...),
    razorpay_signature: str = Form(...),
    user_email: str = Depends(current_user),
) -> JSONResponse:
    """Issue #74 step 3/4: the modal handler's payload, checked for
    authenticity — UX only (B1). A mismatch is a clear failure (B4); a match
    never itself grants the credit (the order.paid webhook does — B1/B3)."""
    settings = request.app.state.settings
    if not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="checkout not switched on")
    ok = razorpay_orders.verify_order_signature(
        settings.razorpay_key_secret, razorpay_order_id, razorpay_payment_id, razorpay_signature
    )
    if not ok:
        raise HTTPException(status_code=400, detail="payment signature could not be verified")
    return JSONResponse({"status": "verified"})


@router.post("/stripe/checkout")
def create_stripe_checkout(
    request: Request, user_email: str = Depends(current_user)
) -> RedirectResponse:
    """Issue #77: create the Stripe Checkout Session server-side, then a
    full-page 303 redirect to Stripe's hosted checkout page — no iframe, no
    client JS. Fulfilment happens on the checkout.session.completed webhook
    (api/routes_webhooks.py); this endpoint never itself grants a credit."""
    settings = request.app.state.settings
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="checkout not switched on")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: same owner-only gate as the plan table and the Razorpay
        # order-create route, checked BEFORE the commit (cold-reviewer #75).
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_BILLING,
            detail="only the workspace owner can buy an audit",
        )
        session.commit()
    base = settings.public_base_url
    try:
        checkout = stripe_checkout.create_session(
            settings.stripe_secret_key,
            settings.one_shot_usd,
            success_url=f"{base}/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/billing?checkout=cancelled",
            email=user_email,
        )
    except stripe_checkout.CheckoutCreateError as exc:
        raise HTTPException(status_code=502, detail="payment provider error") from exc
    return RedirectResponse(url=checkout["url"], status_code=303)
