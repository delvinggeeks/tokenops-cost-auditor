"""T2 source connect/revoke pages (PLAN-V15 WP-1; SSR per the X-05
relaxation — no SPA, no build step).

Key handling per R-CONNECT: the pasted key is encrypted in-request and the
plaintext discarded; it is never logged and never rendered back. Revoke
deletes the ciphertext (crypto.py contract). Connection count is plan-gated
(R-Q5/Q6): free=0, pro=1, team=5 ACTIVE connections; swapping = revoke +
connect.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import Source, Subscription, User, utcnow
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.connectors import validate
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans
from tokenops_cost_auditor.web import help as help_registry

router = APIRouter(prefix="/sources", tags=["sources"])

log = structlog.get_logger("tokenops_cost_auditor.connectors")

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
        active_count = sum(1 for s in sources if s.status == "active")
        # Rendered in the APP shell now, not base.html: the designed sidebar
        # links here, so rendering the old shell navigated users out of the
        # product's own design (v4 unify).
        tpl = request.app.state.jinja.get_template("app/sources.html")
        return HTMLResponse(
            tpl.render(
                sources=sources,
                plan=plan,
                plan_name=plans.get(settings, plan).name,
                limit=settings.plan_source_limits.get(plan, 0),
                active_count=active_count,
                providers=PROVIDERS,
                page="sources",
                purpose=help_registry.purpose("sources"),
                freshness="",
                user_email=user_email,
                show_tour=False,
            )
        )


@router.get("/connect/{provider}", response_class=HTMLResponse)
def wizard_page(
    request: Request, provider: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """The 3-step guided wizard (R-MAGIC-CONNECT §1)."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        plan = user_plan(session, user.id)
        limit = settings.plan_source_limits.get(plan, 0)
        active = (
            session.execute(
                select(Source).where(Source.user_id == user.id, Source.status == "active")
            )
            .scalars()
            .all()
        )
        tpl = request.app.state.jinja.get_template("app/connect_wizard.html")
        return HTMLResponse(
            tpl.render(
                help=help_registry,
                copy=help_registry.wizard(provider),
                provider=provider,
                page="sources",
                plan=plan,
                plan_name=plans.get(settings, plan).name,
                purpose=help_registry.purpose("sources"),
                freshness="",
                user_email=user.email,
                at_limit=len(active) >= limit,
                limit=limit,
                show_tour=False,
            )
        )


@router.post("/connect/{provider}/validate", response_class=HTMLResponse)
def wizard_validate(
    request: Request,
    provider: str,
    api_key: str = Form(...),
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """Live validation, then save. R-WIZ-DEGRADE: an unreachable provider
    saves the key and says so plainly — it never blocks the customer."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    key = api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    settings = request.app.state.settings

    # AUTHORIZE, THEN VALIDATE (V-D9 cold-review f.1): never spend a customer's
    # provider quota — or six seconds of their attention — on a request we
    # already know we will refuse.
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()  # durable regardless of what the validation says (f.2)
        user_id = user.id
        plan = user_plan(session, user_id)
        limit = settings.plan_source_limits.get(plan, 0)
        active = (
            session.execute(
                select(Source).where(Source.user_id == user_id, Source.status == "active")
            )
            .scalars()
            .all()
        )
        if len(active) >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"plan '{plan}' allows {limit} active connection(s) — revoke one first",
            )
        # Idempotency (f.3): a double-submit must not create a second live
        # connection to the same provider, nor a second first-pull.
        if any(s.provider == provider for s in active):
            raise HTTPException(
                status_code=409,
                detail=f"{provider} is already connected — revoke it first to replace it",
            )

    verdict = validate.validate_key(provider, key)

    saved = False
    source_id = ""
    if verdict.can_save:
        with _session(request) as session:
            session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
            still_active = (
                session.execute(
                    select(Source).where(Source.user_id == user_id, Source.status == "active")
                )
                .scalars()
                .all()
            )
            if len(still_active) >= limit or any(s.provider == provider for s in still_active):
                # Someone won the race between our check and this write.
                raise HTTPException(
                    status_code=409, detail=f"{provider} was connected a moment ago"
                )
            source = Source(
                user_id=user_id,
                provider=provider,
                label=f"{provider} usage",
                credentials_encrypted=encrypt_credential(settings.secret_key, key),
            )
            session.add(source)
            auditlog.append(session, user_email, "source.connected", provider)
            session.commit()
            saved = True
            source_id = source.id

    if saved and verdict.status == validate.OK:
        # INSTANT GRATIFICATION (R-MAGIC-CONNECT §2): pull and audit NOW, in
        # the background, so the dashboard has real numbers in this session
        # rather than tomorrow.
        _kickoff_first_pull(request, source_id)

    tpl = request.app.state.jinja.get_template("app/_wizard_verdict.html")
    return HTMLResponse(
        tpl.render(
            verdict=verdict,
            copy=help_registry.wizard(provider),
            provider=provider,
            saved=saved,
        )
    )


def _kickoff_first_pull(request: Request, source_id: str) -> None:
    """Best-effort immediate pull + audit. Failure here NEVER surfaces as a
    connect error — the scheduled tick will do it anyway."""
    import threading

    settings = request.app.state.settings
    factory = request.app.state.session_factory
    table = request.app.state.pricing_table

    def run() -> None:
        from tokenops_cost_auditor.services.connectors.pull import run_pull
        from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit

        try:
            with factory() as session:
                source = session.get(Source, source_id)
                if source is None:
                    return
                run_pull(session, settings, source)
                session.commit()
                run_source_audit(session, settings, table, source)
                session.commit()
        except Exception as exc:
            log.info("connect.first_pull_deferred", error=str(exc)[:160])

    threading.Thread(target=run, daemon=True).start()


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
