"""Magic-link auth routes (FR-17). Rate-limited per NFR-03/NFR-12."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web.auth import (
    SESSION_COOKIE,
    AuthTokenError,
    issue_magic_token,
    issue_session,
    verify_magic_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


@router.post("/magic-link")
@limiter.limit("5/minute")  # NFR-03: auth endpoint rate-limited
def request_magic_link(request: Request, email: str = Form(...)) -> HTMLResponse:
    settings = request.app.state.settings
    email = email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return HTMLResponse(
            status_code=400,
            content="<p>That doesn't look like an email address — please go back "
            "and try again.</p>",
        )
    with _session(request) as session:
        get_or_create_user(session, email)
        auditlog.append(session, email, "auth.magic_link_requested", email)
        session.commit()
    token = issue_magic_token(settings.secret_key, email)
    request.app.state.mail.magic_link(email, f"/auth/verify?token={token}")
    # Same response whether or not the account existed (no enumeration signal).
    return HTMLResponse(
        "<h1>Check your email</h1><p>If that address is valid, a sign-in link is on "
        "its way. The link works once and expires in 15 minutes.</p>"
    )


@router.get("/verify", response_model=None)
def verify(request: Request, token: str) -> HTMLResponse | RedirectResponse:
    settings = request.app.state.settings
    with _session(request) as session:
        # peek at the email without trusting it yet, to load last_login
        try:
            email_unverified = verify_magic_token(settings.secret_key, token, None)
        except AuthTokenError as exc:
            return HTMLResponse(status_code=400, content=f"<h1>Sign-in failed</h1><p>{exc}</p>")
        user = get_or_create_user(session, email_unverified)
        last_login = user.last_login_at
        if last_login is not None and last_login.tzinfo is None:
            # sqlite returns naive datetimes; they are UTC by contract (NFR-11) —
            # naive .timestamp() would wrongly assume LOCAL time
            last_login = last_login.replace(tzinfo=UTC)
        last_login_epoch = last_login.timestamp() if last_login else None
        try:
            email = verify_magic_token(settings.secret_key, token, last_login_epoch)
        except AuthTokenError as exc:  # expired OR already used (single-use, FR-17)
            return HTMLResponse(status_code=400, content=f"<h1>Sign-in failed</h1><p>{exc}</p>")
        user.last_login_at = datetime.now(UTC)  # consumes this and all earlier links
        auditlog.append(session, email, "auth.login", email)
        session.commit()

    # Funnel ruling 3c: every fresh session lands on /dashboard — the product
    # leads with what it found, not with another form. (/upload stays one
    # sidebar click away; v1's land-on-upload behaviour is retired.)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(settings.secret_key, email),
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        # HTTPS-only everywhere it matters. Scoped rather than hard-coded
        # because a secure cookie is never sent over plain http, so on a
        # local dev/preview run the customer signs in and is immediately
        # signed out again — found by the founder-preview build, 2026-07-22.
        # Production is unaffected: app_env=prod keeps secure=True.
        secure=settings.app_env == "prod",
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
