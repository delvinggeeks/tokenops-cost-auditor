"""Server-rendered pages: landing (FR-23), upload (FR-01 web side), legal (runbook §7).

Web layer only (C1) — no SPA (ADR-2/X-05). Session resolution here is
display-only; the API enforces auth separately.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE
from tokenops_cost_auditor.web.auth import SESSION_COOKIE, verify_session

log = structlog.get_logger("tokenops_cost_auditor.web")

router = APIRouter(tags=["pages"])


def _render(request: Request, template: str, **ctx: object) -> HTMLResponse:
    tpl = request.app.state.jinja.get_template(template)
    return HTMLResponse(tpl.render(**ctx))


def session_email(request: Request) -> str | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    settings = request.app.state.settings
    return verify_session(settings.secret_key, cookie, settings.session_ttl_days)


HERO_COOKIE = "hero_v"
HERO_VARIANTS = ("control", "billshock")


def _hero_variant(request: Request) -> str:
    """Cookie-bucketed so a visitor sees ONE hero, not a new one per reload.
    R-PAINMOMENT asked for the bill-shock line to be tested against the
    control narrative; the split is deterministic per visitor, never per
    request."""
    existing = request.cookies.get(HERO_COOKIE)
    if existing in HERO_VARIANTS:
        return existing
    import secrets

    return HERO_VARIANTS[secrets.randbelow(len(HERO_VARIANTS))]


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    variant = _hero_variant(request)
    settings = request.app.state.settings
    # R-PRICING-FINAL-2: ONE currency per viewer (toggle available); launch
    # pricing shows while the market's first-N cohort has room — the flip to
    # list is computed here, in code, from subscription rows.
    ccy_param = request.query_params.get("ccy")
    currency = plans.pick_currency(
        ccy_param,
        request.headers.get("accept-language", ""),
        request.cookies.get("ccy"),
    )
    with request.app.state.session_factory() as db:
        launch = plans.launch_open(db, settings, currency)
    response = _render(
        request,
        "landing.html",
        hero_variant=variant,
        # R-LANDING-2 §8: prices come from THE price config, never inlined —
        # and §7's rail line is the report model's own constant, single-sourced.
        catalogue=[plans.catalogue(settings)[k] for k in plans.ALL_PLANS],
        one_shot=plans.one_shot_display(settings, currency),
        one_shot_billed=plans.one_shot_billed_note(settings, currency),
        currency=currency,
        launch_open=launch,
        cohort_size=settings.launch_cohort_size,
        qualify_spend=f"${settings.qualify_spend_usd:,.0f}",
        equiv_spend_line=EQUIV_SPEND_LINE,
        user_email=session_email(request),
    )
    if request.cookies.get(HERO_COOKIE) != variant:
        response.set_cookie(
            HERO_COOKIE, variant, max_age=30 * 86400, httponly=False, samesite="lax"
        )
    if ccy_param and currency != request.cookies.get("ccy"):
        # an explicit toggle choice persists across pages and visits
        response.set_cookie("ccy", currency, max_age=365 * 86400, httponly=False, samesite="lax")
    log.info("landing.hero", variant=variant)
    return response


@router.post("/early-access", response_class=HTMLResponse)
@limiter.limit("5/minute")  # same family as auth endpoints (NFR-03)
def early_access_signup(request: Request, email: str = Form(...)) -> HTMLResponse:
    """R-GTM-CONTROL: control-plane early-access email capture. No product
    promises, no dates. Signups land in the append-only audit_log (no new
    table) and the daily digest surfaces the weekly count as Phase-2 trigger
    evidence."""
    email = email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return HTMLResponse(
            status_code=400,
            content="<p>That doesn't look like an email address — please go back "
            "and try again.</p>",
        )
    session: Session = request.app.state.session_factory()
    with session:
        auditlog.append(session, email, "early_access.signup", email)
        session.commit()
    return HTMLResponse(
        "<h1>You're on the list</h1><p>We'll email you when spend-control "
        "early access opens. Until then, the audit is the fastest way to take "
        'control — <a href="/upload">start with your logs</a>.</p>'
    )


@router.get("/sample", response_class=HTMLResponse)
def sample_report(request: Request) -> HTMLResponse:
    """FR-16: a shareable sample built by running synthetic fixture traffic
    through the REAL engine — every figure is arithmetic our detectors
    produced, not a mock-up."""
    from tokenops_cost_auditor.services.report import sample

    html = sample.sample_html(request.app.state.settings, request.app.state.pricing_table)
    banner = (
        '<div style="background:#f5f2ec;border-bottom:1px solid #e3ded4;'
        'padding:12px 24px;font:14px system-ui">'
        "<strong>Sample report.</strong> Invented traffic with planted waste, "
        "run through the same engine your logs would use — so the arithmetic is "
        "real even though the company is not. "
        '<a href="/upload">Audit your own logs →</a></div>'
    )
    return HTMLResponse(html.replace("<body>", f"<body>{banner}", 1))


SIGNIN_COPY = {
    # One form, two voices: a returning user wants the door, a first-timer
    # wants to know what they are walking into (wiring item 3b).
    "login": {
        "heading": "Log in",
        "lede": "Enter your email and we'll send you a sign-in link.",
        "submit_label": "Email me a link",
        "show_reassurance": False,
        "show_get_logs": False,
    },
    "signup": {
        "heading": "Start free",
        "lede": "One full audit of your logs, free. No card, no install, "
        "nothing in your request path.",
        "submit_label": "Email me a sign-in link",
        "show_reassurance": True,
        # round 5: /signup's one job is the ask — the counts-note above the
        # form carries the promise; the full get-logs tabs stay on the
        # signed-out /upload variant where teaching IS the job (T-POL-01
        # ordering law holds there: promise before the ask).
        "show_get_logs": False,
    },
}


def _signin_page(request: Request, mode: str, **overrides: object) -> HTMLResponse:
    from tokenops_cost_auditor.web.routes_auth import enabled_federations

    ctx: dict[str, object] = {**SIGNIN_COPY[mode], **overrides}
    # federation buttons render ONLY when configured — a dead button is a
    # promise (R-GTM-CONTROL)
    ctx["federations"] = enabled_federations(request.app.state.settings)
    return _render(request, "signin.html", mode=mode, user_email=None, **ctx)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if session_email(request):
        return RedirectResponse("/dashboard", status_code=303)  # type: ignore[return-value]
    return _signin_page(request, "login")


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request) -> HTMLResponse:
    if session_email(request):
        return RedirectResponse("/dashboard", status_code=303)  # type: ignore[return-value]
    return _signin_page(request, "signup")


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    email = session_email(request)
    if not email:
        # No session means no app nav to render, so the signed-out state is the
        # public shell rather than an app page with an empty sidebar. THIS
        # variant teaches how to get logs (T-POL-01: the counts-only promise
        # travels before the ask), unlike the plain /signup.
        return _signin_page(request, "signup", show_get_logs=True)
    return _render(
        request,
        "app/upload.html",
        user_email=email,
        max_upload_mb=request.app.state.settings.max_upload_mb,
        page="upload",
        plan=None,
        purpose="",
        freshness="",
        show_tour=False,
    )


@router.get("/legal/terms", response_class=HTMLResponse)
def terms(request: Request) -> HTMLResponse:
    # The price in the binding document comes from the SAME config that charges
    # the card (R-ONE-PRICE-CONFIG). It was hardcoded here and had already
    # drifted to a rate we do not charge.
    return _render(
        request,
        "legal/terms.html",
        one_shot=plans.one_shot_terms_display(request.app.state.settings),
    )


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    return _render(request, "legal/privacy.html")


@router.get("/legal/dpa", response_class=HTMLResponse)
def dpa(request: Request) -> HTMLResponse:
    return _render(request, "legal/dpa.html")
