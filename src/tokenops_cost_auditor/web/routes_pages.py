"""Server-rendered pages: landing (FR-23), upload (FR-01 web side), legal (runbook §7).

Web layer only (C1) — no SPA (ADR-2/X-05). Session resolution here is
display-only; the API enforces auth separately.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web.auth import SESSION_COOKIE, verify_session

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


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    return _render(request, "landing.html")


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


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return _render(
        request,
        "upload.html",
        user_email=session_email(request),
        max_upload_mb=request.app.state.settings.max_upload_mb,
    )


@router.get("/legal/terms", response_class=HTMLResponse)
def terms(request: Request) -> HTMLResponse:
    return _render(request, "legal/terms.html")


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    return _render(request, "legal/privacy.html")


@router.get("/legal/dpa", response_class=HTMLResponse)
def dpa(request: Request) -> HTMLResponse:
    return _render(request, "legal/dpa.html")
