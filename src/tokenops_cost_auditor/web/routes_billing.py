"""Billing (PLAN-V15 V-D8 / WP-6).

Shows the plan, what it costs in BOTH currencies (R-Q11), and the state of
any outstanding payment in plain words. No card is ever collected for Free.

Checkout itself is a provider-hosted link — we never see card details.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.payments import plans, subscriptions
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

router = APIRouter(prefix="/billing", tags=["billing"])

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
        ctx = _shell_ctx(session, request, user, "billing")
        return _render(
            request,
            "app/billing.html",
            catalogue=[catalogue[k] for k in plans.ALL_PLANS],
            current=current,
            status=status,
            status_words=STATUS_WORDS.get(status, ""),
            read_only=bool(ent["read_only"]),
            one_shot=plans.one_shot_display(settings),
            razorpay_link=request.app.state.razorpay.payment_link(),
            stripe_link=request.app.state.stripe.payment_link(),
            now=datetime.now(UTC),
            show_tour=False,
            # ctx's plan feeds the topbar badge; billing.html itself reads
            # `current`, so there is no collision — excluding plan rendered
            # an empty badge (seen on the page, not in review).
            **ctx,
        )
