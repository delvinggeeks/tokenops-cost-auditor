"""Magic-link auth routes (FR-17). Rate-limited per NFR-03/NFR-12."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
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

log = structlog.get_logger("tokenops_cost_auditor.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _record_login(session: Session, user: object, email: str, *, first_login: bool) -> None:
    """Shared by the signin-link and federation paths: stamp the login and, on
    the FIRST one, grant the single signup comp credit (R-FREE-CONNECT §2 — the
    one meter for the free audit, either path). Before this the marketed free
    audit 402'd at the payment gate: the promise was unwired.

    The comp grant is idempotent (readiness audit 2026-07-22): `first_login`
    reads last_login_at==None, so two concurrent first-logins (a mail-scanner
    prefetch racing the human click, or a double-click) both saw None and each
    granted a credit. A partial unique index (migration 009) now allows at most
    one comp Payment per user; the SAVEPOINT here swallows the loser of the race
    so the login still succeeds and the meter is granted exactly once."""
    user.last_login_at = datetime.now(UTC)  # type: ignore[attr-defined]
    auditlog.append(session, email, "auth.login", email)
    if not first_login:
        return
    try:
        with session.begin_nested():
            session.add(
                Payment(user_id=user.id, provider="comp", amount=0.0, currency="USD")  # type: ignore[attr-defined]
            )
        auditlog.append(session, email, "credit.signup", email)
    except IntegrityError:
        # the index caught a concurrent grant — the meter already exists
        log.warning("credit.signup_race", email=email)


@router.post("/signin-link")
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
    try:
        request.app.state.mail.magic_link(email, f"/auth/verify?token={token}")
    except Exception as exc:
        # SMTP down/misconfigured must not become an uncaught 500 with no path
        # forward (readiness audit 2026-07-22). Tell the user plainly and log it.
        log.warning("auth.signin_link_send_failed", error=str(exc)[:200])
        return HTMLResponse(
            status_code=502,
            content="<h1>We couldn't send your link just now</h1><p>Something on our "
            "side got in the way of the email. Please try again in a minute — if it "
            f"keeps happening, {settings.support_email} replies within 1 business "
            "day.</p>",
        )
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


# ---------------------------------------------------------------------------
# Signup federation (founder orders 2026-07-27 and 2026-07-21 "why only
# Google"). One registry, one flow: every provider is config-gated by its own
# client id, and every callback lands in the same _record_login — the
# R-FREE-CONNECT one-meter law holds regardless of which door a customer
# walks in through.
#   Google    — OIDC; the email_verified claim is authoritative.
#   Microsoft — Entra ID v2 "common" endpoint (work/school AND personal).
#   GitHub    — plain OAuth2 (no OIDC); the address comes from /user/emails
#               and only one GitHub itself marks verified is accepted.
# Apple is deliberately absent: Sign in with Apple is consumer/iOS-mandated
# and its relay addresses would break the work-email identity this product
# keys everything on (BACKLOG). Enterprise SAML/Okta SSO is X-03 territory
# (multi-org) and stays behind that ruled trigger.
# ---------------------------------------------------------------------------


def _jwt_claims(jwt: str) -> dict:
    """Decode a JWT payload WITHOUT signature verification. Safe here and ONLY
    here: this token came directly from the provider's token endpoint over a
    server-to-server TLS call (confidential-client code flow), never through
    the browser — so its contents are as trustworthy as the TLS channel. Never
    use this on a token that arrived via the user agent."""
    import base64
    import json

    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _google_email(info: object, token: dict) -> str:
    """Trust the address only when Google says it's verified."""
    if isinstance(info, dict) and info.get("email_verified"):
        return str(info.get("email", "")).strip().lower()
    return ""


def _microsoft_email(info: object, token: dict) -> str:
    """SECURITY (nOAuth mitigation, readiness audit 2026-07-22): the /common
    endpoint accepts tokens from ANY Entra tenant, and the userinfo `email`
    claim is admin-settable and unverified — trusting its mere presence let an
    attacker set their tenant email to a victim's address and sign in AS them.
    We now require `xms_edov` (email domain owner verified) TRUE in the
    id_token, which came server-to-server from Microsoft; fail closed without
    it. The Entra app must emit xms_edov as an optional claim (runbook §3a)."""
    claims = _jwt_claims(token.get("id_token", "")) if isinstance(token, dict) else {}
    if not claims.get("xms_edov"):
        return ""
    # take the email ONLY from the verified id_token — never fall back to the
    # mutable userinfo claim (cold-review f.1: that fallback would re-open the
    # nOAuth gap if a token ever carried xms_edov without an email claim)
    return str(claims.get("email", "")).strip().lower()


def _github_email(info: object, token: dict) -> str:
    """/user/emails returns a list; take the primary verified address, else
    any verified one. An unverified-only list is refused the same way an
    email_verified=False claim is."""
    if not isinstance(info, list):
        return ""
    verified = [e for e in info if isinstance(e, dict) and e.get("verified")]
    for entry in verified:
        if entry.get("primary"):
            return str(entry.get("email", "")).strip().lower()
    return str(verified[0].get("email", "")).strip().lower() if verified else ""


@dataclass(frozen=True)
class Federation:
    label: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    extract_email: Callable[[object, dict], str]
    authorize_extra: dict[str, str] = dataclasses.field(default_factory=dict)
    token_headers: dict[str, str] = dataclasses.field(default_factory=dict)


FEDERATIONS: dict[str, Federation] = {
    "google": Federation(
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email",
        extract_email=_google_email,
        authorize_extra={"prompt": "select_account"},
    ),
    "microsoft": Federation(
        label="Microsoft",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        userinfo_url="https://graph.microsoft.com/oidc/userinfo",
        scope="openid email",
        extract_email=_microsoft_email,
    ),
    "github": Federation(
        label="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user/emails",
        scope="user:email",
        extract_email=_github_email,
        # GitHub's token endpoint answers urlencoded unless asked for JSON
        token_headers={"Accept": "application/json"},
    ),
}


def _fed_credentials(settings: object, key: str) -> tuple[str, str]:
    return (
        str(getattr(settings, f"{key}_client_id", "")),
        str(getattr(settings, f"{key}_client_secret", "")),
    )


def _fed_enabled(settings: object, key: str) -> bool:
    # BOTH halves: a client id without its secret renders a button whose
    # callback can never complete — a dead button with extra steps
    client_id, client_secret = _fed_credentials(settings, key)
    return bool(client_id and client_secret)


def enabled_federations(settings: object) -> list[dict[str, str]]:
    """For the sign-in template: which buttons exist at all. A provider
    without its full credential pair has no button and no route — a dead
    button is a promise."""
    return [
        {"key": key, "label": fed.label}
        for key, fed in FEDERATIONS.items()
        if _fed_enabled(settings, key)
    ]


STATE_COOKIE = "oauth_state"


@router.get("/{provider}", response_model=None)
def federation_start(request: Request, provider: str) -> RedirectResponse | HTMLResponse:
    """Config-gated: 404s when the provider isn't fully configured — the
    button never renders in that case either, so this is defense in depth,
    not the primary gate."""
    settings = request.app.state.settings
    fed = FEDERATIONS.get(provider)
    if fed is None or not _fed_enabled(settings, provider):
        return HTMLResponse(status_code=404, content="This sign-in method is not configured.")
    from urllib.parse import urlencode

    # the state is a short-lived signed token — same signer as magic links —
    # AND it is pinned to this browser via an httponly cookie, so the callback
    # only accepts the flow this browser itself started (a validly-signed
    # state from an attacker's own flow fails the cookie comparison)
    state = issue_magic_token(settings.secret_key, "oauth-state")
    params = urlencode(
        {
            "client_id": _fed_credentials(settings, provider)[0],
            "redirect_uri": f"{settings.app_base_url}/auth/{provider}/callback",
            "response_type": "code",
            "scope": fed.scope,
            "state": state,
            **fed.authorize_extra,
        }
    )
    response = RedirectResponse(f"{fed.authorize_url}?{params}", status_code=303)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.app_env == "prod",
        # lax still sends the cookie on the provider's top-level redirect back
        samesite="lax",
    )
    return response


@router.get("/{provider}/callback", response_model=None)
def federation_callback(
    request: Request, provider: str, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse | HTMLResponse:
    settings = request.app.state.settings
    fed = FEDERATIONS.get(provider)
    client_id, client_secret = _fed_credentials(settings, provider)
    if fed is None or not _fed_enabled(settings, provider):
        return HTMLResponse(status_code=404, content="This sign-in method is not configured.")
    fail = HTMLResponse(
        status_code=400,
        content=f"<h1>Sign-in failed</h1><p>{fed.label} sign-in didn't complete — "
        "go back and try again, or use the email link instead. "
        f"Stuck? {settings.support_email} replies within 1 business day.</p>",
    )
    if error or not code:
        return fail
    # CSRF: the state must carry our signature AND match the cookie set when
    # THIS browser started the flow — signature alone would accept a state
    # minted by an attacker starting their own flow
    if not state or request.cookies.get(STATE_COOKIE) != state:
        return fail
    try:
        verify_magic_token(settings.secret_key, state, None)
    except AuthTokenError:
        return fail

    import httpx

    try:
        token = httpx.post(
            fed.token_url,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": f"{settings.app_base_url}/auth/{provider}/callback",
                "grant_type": "authorization_code",
            },
            headers=fed.token_headers,
            timeout=10,
        ).json()
        info = httpx.get(
            fed.userinfo_url,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            timeout=10,
        ).json()
    except Exception as exc:
        # a bad secret or provider outage must be visible server-side, not
        # only in user reports (cold-review f.2)
        log.warning("federation.exchange_failed", provider=provider, error=str(exc)[:200])
        return fail
    email = fed.extract_email(info, token if isinstance(token, dict) else {})
    if not email:
        # an unverified address must not claim an account
        log.warning("federation.email_refused", provider=provider)
        return fail

    with _session(request) as session:
        user = get_or_create_user(session, email)
        _record_login(session, user, email, first_login=user.last_login_at is None)
        auditlog.append(session, email, f"auth.{provider}", email)
        session.commit()

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.delete_cookie(STATE_COOKIE)  # single-use: the flow is complete
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
