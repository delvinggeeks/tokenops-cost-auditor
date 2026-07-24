"""Developer Settings (S-6, R-SDK-PLATFORM) — the management surface.

Mirrors Sentry's Developer Settings: one page where a customer mints personal
READ API tokens (rt_) and registers OAuth applications (third-party apps they
authorize). Token/secret plaintext is shown ONCE and stored only as a keyed
HMAC; revoke DELETES the hash (authority law, parity with ingest keys/devices).

Creating tokens or apps is a Pro deliverable (same law as the ingest key). The
page itself is visible to any signed-in user, with an upsell when not Pro.
"""

from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import (
    ApiToken,
    OAuthApp,
    User,
    new_id,
    utcnow,
)
from tokenops_cost_auditor.persistence.repo import get_or_create_user, workspace_id_for
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web.api_scopes import READ_SCOPES, parse_scopes, scopes_are_known, to_csv
from tokenops_cost_auditor.web.routes_sources import user_plan

router = APIRouter(prefix="/settings/developer", tags=["developer"])

MAX_API_TOKENS_PER_USER = 10
MAX_OAUTH_APPS_PER_USER = 10
MAX_REDIRECT_URIS = 5


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _require_pro(session: Session, user_id: str) -> None:
    if user_plan(session, user_id) not in ("pro", "team"):
        raise HTTPException(
            status_code=403,
            detail="Read tokens and OAuth apps are part of Pro — see /billing",
        )


def _valid_redirect_uri(uri: str) -> bool:
    """Absolute http(s) URL; https required except for loopback (dev)."""
    try:
        p = urlparse(uri)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = p.hostname or ""
    # https anywhere; plain http only for loopback (dev).
    return not (p.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"))


@router.get("", response_class=HTMLResponse)
def developer_home(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        is_pro = user_plan(session, user.id) in ("pro", "team")
        # O-1: developer credentials stay USER-scoped everywhere (list + revoke).
        # A token/app is minted BY and managed BY the individual who created it —
        # Developer Settings shows YOUR tokens, revoke affects YOUR tokens. (The
        # workspace-scoping that matters is on the DATA a token grants: the read
        # API scopes to the token-owner's active workspace — see routes_api_read.
        # Workspace-wide credential administration is an O-2 RBAC admin surface.)
        tokens = (
            session.execute(
                select(ApiToken)
                .where(ApiToken.user_id == user.id, ApiToken.token_hash.is_not(None))
                .order_by(ApiToken.created_at.desc())
            )
            .scalars()
            .all()
        )
        apps = (
            session.execute(
                select(OAuthApp)
                .where(OAuthApp.owner_user_id == user.id, OAuthApp.revoked_at.is_(None))
                .order_by(OAuthApp.created_at.desc())
            )
            .scalars()
            .all()
        )
        token_view = [
            {
                "id": t.id,
                "label": t.label,
                "scopes": parse_scopes(t.scopes),
                "created_at": t.created_at,
                "last_used_at": t.last_used_at,
            }
            for t in tokens
        ]
        app_view = [
            {
                "id": a.id,
                "name": a.name,
                "client_id": a.client_id,
                "scopes": parse_scopes(a.scopes),
                "redirect_uris": [u for u in a.redirect_uris.splitlines() if u.strip()],
            }
            for a in apps
        ]
    tpl = request.app.state.jinja.get_template("app/developer.html")
    return HTMLResponse(
        tpl.render(
            user_email=user_email,
            is_pro=is_pro,
            tokens=token_view,
            apps=app_view,
            all_scopes=READ_SCOPES,
            page="developer",
            plan_name="Pro" if is_pro else "",
            purpose="Read your audits from your own code, or let an app you trust read them.",
            freshness="",
        )
    )


@router.post("/tokens", response_class=HTMLResponse)
@limiter.limit("5/minute")
def mint_token(
    request: Request,
    label: str = Form("read token"),
    scopes: Annotated[list[str] | None, Form()] = None,
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """Mint a personal READ token — shown once, stored hashed."""
    granted = to_csv([s for s in (scopes or []) if s in READ_SCOPES])
    if not granted:
        raise HTTPException(status_code=400, detail="select at least one read scope")
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        _require_pro(session, user.id)
        active = session.execute(
            select(ApiToken).where(ApiToken.user_id == user.id, ApiToken.token_hash.is_not(None))
        ).scalars()
        if len(list(active)) >= MAX_API_TOKENS_PER_USER:
            raise HTTPException(
                status_code=403,
                detail=f"{MAX_API_TOKENS_PER_USER} active tokens is the limit — revoke one first",
            )
        token = f"rt_{secrets.token_urlsafe(32)}"
        session.add(
            ApiToken(
                user_id=user.id,
                workspace_id=workspace_id_for(session, user.id),  # O-0
                label=label.strip()[:80] or "read token",
                token_hash=credential_fingerprint(settings.secret_key, token),
                scopes=granted,
            )
        )
        auditlog.append(session, user_email, "api.token_minted", label.strip()[:80])
        session.commit()
    tpl = request.app.state.jinja.get_template("app/_api_token.html")
    return HTMLResponse(tpl.render(token=token, scopes=parse_scopes(granted)))


@router.post("/tokens/{token_id}/revoke")
def revoke_token(
    request: Request, token_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        row = session.get(ApiToken, token_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="token not found")
        row.token_hash = None  # authority law: material deleted
        row.revoked_at = utcnow()
        auditlog.append(session, user_email, "api.token_revoked", row.label)
        session.commit()
    return RedirectResponse("/settings/developer", status_code=303)


@router.post("/apps", response_class=HTMLResponse)
@limiter.limit("5/minute")
def register_app(
    request: Request,
    name: str = Form(""),
    redirect_uris: str = Form(""),
    scopes: Annotated[list[str] | None, Form()] = None,
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """Register a third-party OAuth app. client_secret is shown ONCE."""
    scopes = scopes or []
    name = name.strip()[:80]
    if not name:
        raise HTTPException(status_code=400, detail="give the application a name")
    uris = [u.strip() for u in redirect_uris.replace(",", "\n").splitlines() if u.strip()]
    if not uris or len(uris) > MAX_REDIRECT_URIS:
        raise HTTPException(
            status_code=400,
            detail=f"list 1 to {MAX_REDIRECT_URIS} redirect URIs, one per line",
        )
    if not all(_valid_redirect_uri(u) for u in uris):
        raise HTTPException(
            status_code=400,
            detail="each redirect URI must be an absolute https URL (http only for localhost)",
        )
    granted = to_csv([s for s in scopes if s in READ_SCOPES])
    if not granted or not scopes_are_known(" ".join(scopes)):
        raise HTTPException(status_code=400, detail="select at least one valid read scope")

    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        _require_pro(session, user.id)
        active = session.execute(
            select(OAuthApp).where(OAuthApp.owner_user_id == user.id, OAuthApp.revoked_at.is_(None))
        ).scalars()
        if len(list(active)) >= MAX_OAUTH_APPS_PER_USER:
            raise HTTPException(
                status_code=403,
                detail=f"{MAX_OAUTH_APPS_PER_USER} apps is the limit — revoke one first",
            )
        client_id = f"oac_{secrets.token_urlsafe(16)}"
        client_secret = f"oas_{secrets.token_urlsafe(32)}"
        session.add(
            OAuthApp(
                id=new_id(),
                owner_user_id=user.id,
                workspace_id=workspace_id_for(session, user.id),  # O-0
                name=name,
                client_id=client_id,
                client_secret_hash=credential_fingerprint(settings.secret_key, client_secret),
                redirect_uris="\n".join(uris),
                scopes=granted,
            )
        )
        auditlog.append(session, user_email, "oauth.app_registered", name)
        session.commit()
    tpl = request.app.state.jinja.get_template("app/_oauth_secret.html")
    return HTMLResponse(
        tpl.render(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            scopes=parse_scopes(granted),
        )
    )


@router.post("/apps/{app_id}/revoke")
def revoke_app(
    request: Request, app_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    """Revoke an app: its secret is deleted AND every access token it issued
    dies (the resolver rejects tokens of a revoked app)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        row = session.get(OAuthApp, app_id)
        if row is None or row.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="app not found")
        row.client_secret_hash = None
        row.revoked_at = utcnow()
        auditlog.append(session, user_email, "oauth.app_revoked", row.name)
        session.commit()
    return RedirectResponse("/settings/developer", status_code=303)
