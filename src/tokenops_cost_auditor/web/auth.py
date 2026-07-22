"""Magic-link + session primitives (FR-17; docs/02-HLD.md §6).

Magic link: signed token, 15-minute expiry, SINGLE-USE — consumption bumps
users.last_login_at, and any token issued at-or-before that instant is dead
(no consumed-token table needed; all earlier links die on login, which is
strictly safer). Session: signed cookie (HttpOnly, Secure, SameSite=Lax),
SESSION_TTL_DAYS expiry (accepted default Q11).
"""

from __future__ import annotations

import time

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

MAGIC_SALT = "tokenops-cost-auditor.magic-link.v1"
SESSION_SALT = "tokenops-cost-auditor.session.v1"
MAGIC_LINK_MAX_AGE_S = 15 * 60  # HLD §6
SESSION_COOKIE = "top_session"


class AuthTokenError(Exception):
    """Invalid, expired or already-used token. Message is user-safe."""


def issue_magic_token(secret_key: str, email: str) -> str:
    # float epoch: same-second re-issue after a login must remain usable
    # (G5 cold-reviewer f.2); <= comparison still blocks same-token replay
    payload = {"email": email.lower(), "iat": time.time()}
    return str(URLSafeTimedSerializer(secret_key, salt=MAGIC_SALT).dumps(payload))


def verify_magic_token(secret_key: str, token: str, last_login_epoch: float | None) -> str:
    """Returns the email. last_login_epoch enforces single use: tokens issued
    at-or-before the last successful login are rejected."""
    serializer = URLSafeTimedSerializer(secret_key, salt=MAGIC_SALT)
    try:
        payload = serializer.loads(token, max_age=MAGIC_LINK_MAX_AGE_S)
    except SignatureExpired as exc:
        raise AuthTokenError("this sign-in link has expired — request a new one") from exc
    except BadSignature as exc:
        raise AuthTokenError("invalid sign-in link") from exc
    if last_login_epoch is not None and float(payload["iat"]) <= last_login_epoch:
        raise AuthTokenError("this sign-in link was already used — request a new one")
    return str(payload["email"])


def issue_session(secret_key: str, email: str) -> str:
    return str(URLSafeTimedSerializer(secret_key, salt=SESSION_SALT).dumps(email.lower()))


def verify_session(secret_key: str, cookie_value: str, ttl_days: int) -> str | None:
    """The email a session cookie proves, or None. Signature + TTL only — the
    per-user session-epoch check (revocation) lives in resolve_session, which
    also has the DB. Kept for callers that only need the email."""
    result = verify_session_ts(secret_key, cookie_value, ttl_days)
    return result[0] if result else None


def verify_session_ts(
    secret_key: str, cookie_value: str, ttl_days: int
) -> tuple[str, float] | None:
    """(email, issued_epoch) or None. The issued time lets the caller reject a
    cookie minted before the user's sessions_valid_from — real revocation over
    a stateless signed cookie (readiness audit 2026-07-22)."""
    import datetime as _dt

    serializer = URLSafeTimedSerializer(secret_key, salt=SESSION_SALT)
    try:
        email, issued = serializer.loads(
            cookie_value, max_age=ttl_days * 86400, return_timestamp=True
        )
    except BadSignature:  # includes SignatureExpired
        return None
    ts = issued.replace(tzinfo=_dt.UTC).timestamp() if issued.tzinfo is None else issued.timestamp()
    return str(email), ts


def resolve_session(request: object, secret_key: str, ttl_days: int) -> str | None:
    """The authenticated email for this request, honoring the per-user session
    epoch. A cookie issued at-or-before the user's sessions_valid_from is dead
    (log-out-everywhere / close-account). One indexed lookup per request."""
    import datetime as _dt

    cookie = request.cookies.get(SESSION_COOKIE)  # type: ignore[attr-defined]
    if not cookie:
        return None
    parsed = verify_session_ts(secret_key, cookie, ttl_days)
    if parsed is None:
        return None
    email, issued_ts = parsed
    from sqlalchemy import select

    from tokenops_cost_auditor.persistence.models import User

    with request.app.state.session_factory() as session:  # type: ignore[attr-defined]
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            return email  # no account row yet (first federated login mid-flight)
        cut = user.sessions_valid_from
        if cut is not None:
            cut_ts = (cut.replace(tzinfo=_dt.UTC) if cut.tzinfo is None else cut).timestamp()
            # itsdangerous floors the issued time to whole seconds, so the +1
            # avoids false-rejecting a legitimately fresh cookie. Trade-off: a
            # cookie issued in the <1s before the epoch bump survives — a
            # negligible window for a deliberate close/logout action.
            if issued_ts + 1 < cut_ts:
                return None
    return email
