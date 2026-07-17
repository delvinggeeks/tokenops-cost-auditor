"""Signed, expiring report URLs (FR-15; accepted default Q9: 30-day expiry).

itsdangerous URLSafeTimedSerializer; tokens carry only the audit id — tampering
or expiry raises SignedUrlError (user-safe message, no internals).
"""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "tokenops-cost-auditor.report-url.v1"


class SignedUrlError(Exception):
    """Invalid, tampered or expired report link."""


def sign_report_url(secret_key: str, audit_id: str) -> str:
    return str(URLSafeTimedSerializer(secret_key, salt=SALT).dumps(audit_id))


def verify_report_url(secret_key: str, token: str, max_age_days: int) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt=SALT)
    try:
        audit_id = serializer.loads(token, max_age=max_age_days * 86400)
    except SignatureExpired as exc:
        raise SignedUrlError("this report link has expired — request a fresh one") from exc
    except BadSignature as exc:
        raise SignedUrlError("invalid report link") from exc
    return str(audit_id)
