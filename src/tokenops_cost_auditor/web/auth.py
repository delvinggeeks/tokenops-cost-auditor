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
    payload = {"email": email.lower(), "iat": int(time.time())}
    return str(URLSafeTimedSerializer(secret_key, salt=MAGIC_SALT).dumps(payload))


def verify_magic_token(secret_key: str, token: str, last_login_epoch: int | None) -> str:
    """Returns the email. last_login_epoch enforces single use: tokens issued
    at-or-before the last successful login are rejected."""
    serializer = URLSafeTimedSerializer(secret_key, salt=MAGIC_SALT)
    try:
        payload = serializer.loads(token, max_age=MAGIC_LINK_MAX_AGE_S)
    except SignatureExpired as exc:
        raise AuthTokenError("this sign-in link has expired — request a new one") from exc
    except BadSignature as exc:
        raise AuthTokenError("invalid sign-in link") from exc
    if last_login_epoch is not None and int(payload["iat"]) <= last_login_epoch:
        raise AuthTokenError("this sign-in link was already used — request a new one")
    return str(payload["email"])


def issue_session(secret_key: str, email: str) -> str:
    return str(URLSafeTimedSerializer(secret_key, salt=SESSION_SALT).dumps(email.lower()))


def verify_session(secret_key: str, cookie_value: str, ttl_days: int) -> str | None:
    serializer = URLSafeTimedSerializer(secret_key, salt=SESSION_SALT)
    try:
        return str(serializer.loads(cookie_value, max_age=ttl_days * 86400))
    except BadSignature:  # includes SignatureExpired
        return None
