"""Magic-link auth routes (FR-17). Rate-limited per NFR-03/NFR-12."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import Payment
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


def _record_login(session: Session, user: object, email: str, *, first_login: bool) -> None:
    """Shared by the magic-link and Google paths: stamp the login and, on the
    FIRST one, grant the single signup comp credit (R-FREE-CONNECT §2 — the
    one meter for the free audit, either path). Before this the marketed free
    audit 402'd at the payment gate: the promise was unwired."""
    user.last_login_at = datetime.now(UTC)  # type: ignore[attr-defined]
    auditlog.append(session, email, "auth.login", email)
    if first_login:
        session.add(
            Payment(user_id=user.id, provider="comp", amount=0.0, currency="USD")  # type: ignore[attr-defined]
        )
        auditlog.append(session, email, "credit.signup", email)


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
        _record_login(session, user, email, first_login=last_login is None)
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


GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


@router.get("/google", response_model=None)
def google_start(request: Request) -> RedirectResponse | HTMLResponse:
    """Signup federation (founder order 2026-07-27). Config-gated: 404s when
    no client id is configured — the button never renders in that case either,
    so this is defense in depth, not the primary gate."""
    settings = request.app.state.settings
    if not settings.google_client_id:
        return HTMLResponse(status_code=404, content="Google sign-in is not configured.")
    from urllib.parse import urlencode

    # the state is a short-lived signed token — same signer as magic links,
    # so CSRF on the callback costs an attacker the same forgery we already
    # made impossible for sessions
    state = issue_magic_token(settings.secret_key, "oauth-state")
    params = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.app_base_url}/auth/google/callback",
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "prompt": "select_account",
        }
    )
    return RedirectResponse(f"{GOOGLE_AUTHORIZE}?{params}", status_code=303)


@router.get("/google/callback", response_model=None)
def google_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse | HTMLResponse:
    settings = request.app.state.settings
    if not settings.google_client_id:
        return HTMLResponse(status_code=404, content="Google sign-in is not configured.")
    fail = HTMLResponse(
        status_code=400,
        content="<h1>Sign-in failed</h1><p>Google sign-in didn't complete — "
        "go back and try again, or use the email link instead. "
        "Stuck? support@tokenops.cloud replies within 1 business day.</p>",
    )
    if error or not code:
        return fail
    try:
        verify_magic_token(settings.secret_key, state, None)  # CSRF state check
    except AuthTokenError:
        return fail

    import httpx

    try:
        token = httpx.post(
            GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.app_base_url}/auth/google/callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        ).json()
        info = httpx.get(
            GOOGLE_USERINFO,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            timeout=10,
        ).json()
    except Exception:
        return fail
    email = str(info.get("email", "")).strip().lower()
    if not email or not info.get("email_verified"):
        # an unverified Google address must not claim an account
        return fail

    with _session(request) as session:
        user = get_or_create_user(session, email)
        _record_login(session, user, email, first_login=user.last_login_at is None)
        auditlog.append(session, email, "auth.google", email)
        session.commit()

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(settings.secret_key, email),
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.app_env == "prod",
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
