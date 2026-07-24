"""OAuth 2.0 authorization server (S-6, R-SDK-PLATFORM).

The authorization-code grant WITH PKCE (RFC 6749 + RFC 7636), read-scoped only.
A customer authorizes a third-party app to READ their audits/findings; the app
never proxies or gates the customer's LLM traffic (X-01/X-02 hold) and can only
ever hold read scopes (api_scopes.READ_SCOPES).

Security invariants (each is adversarially checked at the gate):
- redirect_uri is matched BYTE-EXACT against the app's registered set. An
  unknown client_id or redirect_uri is shown an on-site error page and is
  NEVER redirected to — the open-redirect / mix-up guard.
- The consent POST is bound to the logged-in resource owner via a signed,
  short-TTL request blob (issued only after the GET validated everything) whose
  embedded email must equal the session email — signature + binding = CSRF-safe.
- PKCE S256 is REQUIRED for every app; the token exchange proves the verifier.
- The client_secret is ALSO required and compared as a keyed HMAC (confidential
  client). Both PKCE and secret must pass.
- Authorization codes are single-use (burned via an atomic conditional UPDATE,
  correct on both backends) and short-TTL; a redeemed or expired code is
  invalid_grant.
- The issued access token is read-scoped, tenant-bound to the owner, and dies
  when the app is revoked.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select, update

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import (
    OAuthAccessToken,
    OAuthApp,
    OAuthAuthCode,
    utcnow,
)
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.web.api_scopes import READ_SCOPES, is_subset, parse_scopes, to_csv

router = APIRouter(prefix="/oauth", tags=["oauth"])

_REQUEST_SALT = "oauth-authorize-request"  # itsdangerous salt for the consent blob
_REQUEST_TTL_SECONDS = 600  # a consent decision must land within 10 minutes
_CODE_TTL_SECONDS = 300  # an authorization code lives 5 minutes
_ACCESS_TTL_DAYS = 30  # issued access tokens expire after 30 days


# ---------- helpers ----------


def _aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive DB datetime (SQLite drops tzinfo) to aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _registered_uris(app: OAuthApp) -> list[str]:
    return [u.strip() for u in app.redirect_uris.splitlines() if u.strip()]


def _pkce_ok(verifier: str, challenge: str) -> bool:
    """RFC 7636 S256: base64url(sha256(verifier)) == challenge, constant-time.

    The verifier is ASCII by spec ([A-Za-z0-9-._~]); a non-ASCII one is simply an
    invalid verifier, so encode failure returns False (→ opaque invalid_grant)
    rather than raising an uncaught 500 (cold-reviewer f.2)."""
    if not verifier or not challenge:
        return False
    try:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
    except UnicodeEncodeError:
        return False
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, challenge)


def _redirect_with(uri: str, params: dict[str, str]) -> RedirectResponse:
    sep = "&" if "?" in uri else "?"
    return RedirectResponse(f"{uri}{sep}{urlencode(params)}", status_code=302)


def _error_page(request: Request, title: str, detail: str, status: int = 400) -> HTMLResponse:
    tpl = request.app.state.jinja.get_template("oauth/error.html")
    return HTMLResponse(status_code=status, content=tpl.render(title=title, detail=detail))


def _session_email(request: Request) -> str | None:
    """The authenticated resource owner, or None. Honors the real session cookie
    AND (non-prod only) the X-User-Email dev shim — the same resolution as
    current_user, but returning None instead of raising 401."""
    try:
        return current_user(request, request.headers.get("x-user-email"))
    except HTTPException:
        return None


def _serializer(request: Request) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(request.app.state.settings.secret_key, salt=_REQUEST_SALT)


# ---------- authorization endpoint ----------


@router.get("/authorize", response_model=None)
def authorize(
    request: Request,
    response_type: str = "",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
) -> Response:
    """Validate the request, then render the consent screen for the logged-in
    resource owner. Client/redirect problems render on-site (never redirect)."""
    with request.app.state.session_factory() as session:
        app = session.execute(
            select(OAuthApp).where(OAuthApp.client_id == client_id, OAuthApp.revoked_at.is_(None))
        ).scalar_one_or_none()
        if app is None:
            return _error_page(request, "Unknown application", "That client_id is not registered.")
        registered = _registered_uris(app)
        if redirect_uri not in registered:
            return _error_page(
                request,
                "redirect_uri mismatch",
                "This redirect_uri is not registered for the application.",
            )
        app_name, app_scopes_csv = app.name, app.scopes

    # From here a request error CAN be reported to the client via redirect_uri
    # (it is proven-registered), per RFC 6749 §4.1.2.1.
    if response_type != "code":
        return _redirect_with(redirect_uri, _err("unsupported_response_type", state))
    if code_challenge_method != "S256" or not code_challenge:
        return _redirect_with(redirect_uri, _err("invalid_request", state))
    requested = to_csv(parse_scopes(scope)) if scope else app_scopes_csv
    if not requested or not is_subset(requested, app_scopes_csv):
        return _redirect_with(redirect_uri, _err("invalid_scope", state))

    email = _session_email(request)
    if not email:
        tpl = request.app.state.jinja.get_template("oauth/authorize.html")
        return HTMLResponse(
            tpl.render(needs_login=True, app_name=app_name, scopes=[], auth_request="")
        )

    blob = _serializer(request).dumps(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": requested,
            "state": state,
            "code_challenge": code_challenge,
            "email": email,
        }
    )
    tpl = request.app.state.jinja.get_template("oauth/authorize.html")
    return HTMLResponse(
        tpl.render(
            needs_login=False,
            app_name=app_name,
            scopes=[(s, READ_SCOPES[s]) for s in parse_scopes(requested)],
            auth_request=blob,
        )
    )


def _err(code: str, state: str) -> dict[str, str]:
    params = {"error": code}
    if state:
        params["state"] = state
    return params


@router.post("/authorize", response_model=None)
def authorize_decision(
    request: Request,
    auth_request: str = Form(""),
    decision: str = Form(""),
) -> Response:
    """Approve or deny. The signed blob binds this decision to the resource
    owner who started the flow — a forged/cross-user POST fails the email check."""
    try:
        payload = _serializer(request).loads(auth_request, max_age=_REQUEST_TTL_SECONDS)
    except SignatureExpired:
        return _error_page(request, "This request expired", "Start the authorization again.")
    except BadSignature:
        return _error_page(request, "Invalid request", "This authorization request is not valid.")

    email = _session_email(request)
    # CSRF + resource-owner binding: the decision only counts for the user the
    # blob was minted for, and only while they are the one logged in now.
    if not email or email != payload.get("email"):
        return _error_page(request, "Session mismatch", "Sign in again and retry.", status=403)

    redirect_uri = str(payload["redirect_uri"])
    state = str(payload.get("state", ""))

    with request.app.state.session_factory() as session:
        app = session.execute(
            select(OAuthApp).where(
                OAuthApp.client_id == payload["client_id"], OAuthApp.revoked_at.is_(None)
            )
        ).scalar_one_or_none()
        # Defense in depth: the app could have been revoked, its redirect set
        # edited, or its scopes reduced between the GET and this POST.
        if app is None or redirect_uri not in _registered_uris(app):
            return _error_page(request, "Application unavailable", "The application was revoked.")

        if decision != "approve":
            return _redirect_with(redirect_uri, _err("access_denied", state))

        if not is_subset(str(payload["scope"]), app.scopes):
            return _redirect_with(redirect_uri, _err("invalid_scope", state))

        from tokenops_cost_auditor.persistence.models import User

        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            return _error_page(request, "Account not found", "Sign in again and retry.", status=403)

        code = f"oaq_{secrets.token_urlsafe(32)}"
        secret = request.app.state.settings.secret_key
        session.add(
            OAuthAuthCode(
                code_hash=credential_fingerprint(secret, code),
                app_id=app.id,
                user_id=user.id,
                redirect_uri=redirect_uri,
                scopes=str(payload["scope"]),
                code_challenge=str(payload["code_challenge"]),
                expires_at=utcnow() + timedelta(seconds=_CODE_TTL_SECONDS),
            )
        )
        session.commit()

    params = {"code": code}
    if state:
        params["state"] = state
    return _redirect_with(redirect_uri, params)


# ---------- token endpoint (RFC 6749 §5.2 error format) ----------


def _oauth_error(code: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code})


@router.post("/token", response_model=None)
def token(
    request: Request,
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    code_verifier: str = Form(""),
) -> Response:
    """Exchange a single-use authorization code for a read-scoped access token.
    Requires BOTH the client_secret (confidential client) and the PKCE verifier."""
    if grant_type != "authorization_code":
        return _oauth_error("unsupported_grant_type")
    secret = request.app.state.settings.secret_key

    with request.app.state.session_factory() as session:
        app = session.execute(
            select(OAuthApp).where(OAuthApp.client_id == client_id, OAuthApp.revoked_at.is_(None))
        ).scalar_one_or_none()
        if (
            app is None
            or app.client_secret_hash is None
            or not hmac.compare_digest(
                app.client_secret_hash, credential_fingerprint(secret, client_secret)
            )
        ):
            return _oauth_error("invalid_client", status=401)

        code_fp = credential_fingerprint(secret, code)
        row = session.execute(
            select(OAuthAuthCode).where(OAuthAuthCode.code_hash == code_fp)
        ).scalar_one_or_none()
        now = utcnow()
        if (
            row is None
            or row.app_id != app.id
            or row.consumed_at is not None
            or _aware(row.expires_at) <= now
            or row.redirect_uri != redirect_uri
            or not _pkce_ok(code_verifier, row.code_challenge)
        ):
            # Single-use replay, expiry, wrong client, tampered redirect, bad
            # PKCE — all collapse to one opaque invalid_grant (no oracle).
            return _oauth_error("invalid_grant")

        # Burn the code atomically: a conditional UPDATE that only ONE concurrent
        # redemption can win (rowcount == 1). This is correct on BOTH backends —
        # `FOR UPDATE` is a no-op on SQLite, so single-use must not depend on it
        # (cold-reviewer f.1). The loser of the race sees rowcount 0 here.
        burned = session.execute(
            update(OAuthAuthCode)
            .where(OAuthAuthCode.code_hash == code_fp, OAuthAuthCode.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        if burned.rowcount != 1:
            return _oauth_error("invalid_grant")

        access = f"at_{secrets.token_urlsafe(32)}"
        session.add(
            OAuthAccessToken(
                app_id=app.id,
                user_id=row.user_id,
                token_hash=credential_fingerprint(secret, access),
                scopes=row.scopes,
                expires_at=now + timedelta(days=_ACCESS_TTL_DAYS),
            )
        )
        granted = row.scopes
        session.commit()

    return JSONResponse(
        status_code=200,
        content={
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": _ACCESS_TTL_DAYS * 86400,
            "scope": granted,
        },
    )
