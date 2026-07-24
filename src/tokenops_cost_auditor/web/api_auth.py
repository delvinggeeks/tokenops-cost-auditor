"""Read-API bearer authentication (S-6, R-SDK-PLATFORM).

One resolver for both READ credentials:

- ``rt_…`` — a personal API token (ApiToken), minted in Developer Settings.
- ``at_…`` — an OAuth access token (OAuthAccessToken), issued to a third-party
  app the user authorized.

Both hash to a keyed HMAC (credential_fingerprint) and both carry a scope set;
neither can write. The resolver yields a ReadPrincipal — the owning user_id
and the granted scopes — and NEVER the token itself. Tenancy lives here at the
web boundary: downstream read handlers scope every query to the principal's
ACTIVE WORKSPACE (O-1, R-ORG: repo.active_workspace_id(principal.user_id)) —
so a read token returns the token-owner's workspace data, shared with its
members — while the audit engine never learns a token or a workspace exists.

Every failure raises HTTPException under /api/ → the NFR-14 envelope.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    ApiToken,
    OAuthAccessToken,
    OAuthApp,
    utcnow,
)
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.web.api_scopes import parse_scopes


@dataclass(frozen=True)
class ReadPrincipal:
    user_id: str
    scopes: frozenset[str]
    kind: str  # "api_token" | "oauth"


_UNAUTH = "send a read token: Authorization: Bearer rt_… (mint one in Developer Settings)"


def _aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive DB datetime (SQLite drops tzinfo) to aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def resolve_read_bearer(request: Request, authorization: str | None) -> ReadPrincipal:
    """Authorization header -> ReadPrincipal, or 401. Stamps last_used_at."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=_UNAUTH)
    token = authorization.removeprefix("Bearer ").strip()
    secret = request.app.state.settings.secret_key
    fp = credential_fingerprint(secret, token)
    now = utcnow()

    with _session(request) as session:
        if token.startswith("rt_"):
            api_row = session.execute(
                select(ApiToken).where(ApiToken.token_hash == fp, ApiToken.token_hash.is_not(None))
            ).scalar_one_or_none()
            if api_row is None:
                raise HTTPException(status_code=401, detail="unknown or revoked API token")
            api_row.last_used_at = now
            principal = ReadPrincipal(
                api_row.user_id, frozenset(parse_scopes(api_row.scopes)), "api_token"
            )
            session.commit()
            return principal

        if token.startswith("at_"):
            oauth_row = session.execute(
                select(OAuthAccessToken).where(
                    OAuthAccessToken.token_hash == fp,
                    OAuthAccessToken.token_hash.is_not(None),
                )
            ).scalar_one_or_none()
            if oauth_row is None:
                raise HTTPException(status_code=401, detail="unknown or revoked access token")
            if _aware(oauth_row.expires_at) <= now:
                raise HTTPException(status_code=401, detail="access token expired")
            # A revoked app kills every token it ever issued, even unexpired ones.
            app = session.get(OAuthApp, oauth_row.app_id)
            if app is None or app.revoked_at is not None:
                raise HTTPException(status_code=401, detail="the authorizing app was revoked")
            oauth_row.last_used_at = now
            principal = ReadPrincipal(
                oauth_row.user_id, frozenset(parse_scopes(oauth_row.scopes)), "oauth"
            )
            session.commit()
            return principal

    raise HTTPException(status_code=401, detail=_UNAUTH)


def require_read_scope(scope: str) -> Callable[[Request, str | None], ReadPrincipal]:
    """FastAPI dependency factory: resolve the bearer AND assert one scope.

    Usage: ``principal: ReadPrincipal = Depends(require_read_scope("read:audits"))``.
    A valid token missing the scope is 403 (forbidden) — never 401, so a client
    can tell "your token is fine but lacks this scope" from "your token is bad".
    """

    def _dep(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> ReadPrincipal:
        principal = resolve_read_bearer(request, authorization)
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"this token lacks the '{scope}' scope",
            )
        return principal

    return _dep
