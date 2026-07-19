"""T2 source connect/revoke pages (PLAN-V15 WP-1; SSR per the X-05
relaxation — no SPA, no build step).

Key handling per R-CONNECT: the pasted key is encrypted in-request and the
plaintext discarded; it is never logged and never rendered back. Revoke
deletes the ciphertext (crypto.py contract). Connection count is plan-gated
(R-Q5/Q6): free=0, pro=1, team=5 ACTIVE connections; swapping = revoke +
connect.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import Source, Subscription, User, utcnow
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.lifecycle import auditlog

router = APIRouter(prefix="/sources", tags=["sources"])

PROVIDERS = ("openai", "anthropic")


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def user_plan(session: Session, user_id: str) -> str:
    sub = session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    ).scalar_one_or_none()
    if sub is None or sub.status == "cancelled":
        return "free"
    return sub.plan


@router.get("", response_class=HTMLResponse)
def sources_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    settings = request.app.state.settings
    with _session(request) as session:
        user = session.execute(select(User).where(User.email == user_email)).scalar_one_or_none()
        sources = (
            session.execute(
                select(Source)
                .where(Source.user_id == user.id, Source.status != "revoked")
                .order_by(Source.created_at)
            )
            .scalars()
            .all()
            if user
            else []
        )
        plan = user_plan(session, user.id) if user else "free"
        tpl = request.app.state.jinja.get_template("sources.html")
        return HTMLResponse(
            tpl.render(
                sources=sources,
                plan=plan,
                limit=settings.plan_source_limits.get(plan, 0),
                providers=PROVIDERS,
            )
        )


@router.post("", response_model=None)
def connect_source(
    request: Request,
    user_email: str = Depends(current_user),
    provider: str = Form(...),
    label: str = Form(...),
    api_key: str = Form(...),
) -> RedirectResponse:
    settings = request.app.state.settings
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="unknown provider")
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="key required")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        plan = user_plan(session, user.id)
        limit = settings.plan_source_limits.get(plan, 0)
        # Lock the user row so concurrent connects serialize on the count
        # (G-V1 cold-reviewer f.1: read-then-insert raced past the plan cap).
        # Row lock on Postgres; no-op on SQLite.
        session.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        active = (
            session.execute(
                select(Source).where(Source.user_id == user.id, Source.status == "active")
            )
            .scalars()
            .all()
        )
        if len(active) >= limit:
            # R-Q5: free has no connections; swapping = revoke + connect
            raise HTTPException(
                status_code=403,
                detail=f"plan '{plan}' allows {limit} active connection(s) — revoke one first",
            )
        session.add(
            Source(
                user_id=user.id,
                provider=provider,
                label=label.strip()[:120] or provider,
                credentials_encrypted=encrypt_credential(settings.secret_key, api_key.strip()),
            )
        )
        auditlog.append(session, user.email, "source.connected", provider)
        session.commit()
    return RedirectResponse("/sources", status_code=303)


@router.post("/{source_id}/revoke", response_model=None)
def revoke_source(
    request: Request, source_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        source = session.get(Source, source_id)
        if source is None or source.user_id != user.id:
            raise HTTPException(status_code=404, detail="source not found")
        source.status = "revoked"
        source.credentials_encrypted = None  # ciphertext deleted, not just flagged
        source.revoked_at = utcnow()
        auditlog.append(session, user.email, "source.revoked", source.provider)
        session.commit()
    return RedirectResponse("/sources", status_code=303)
