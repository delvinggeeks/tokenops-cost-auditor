"""T2 source connect/revoke pages (PLAN-V15 WP-1; SSR per the X-05
relaxation — no SPA, no build step).

Key handling per R-CONNECT: the pasted key is encrypted in-request and the
plaintext discarded; it is never logged and never rendered back. Revoke
deletes the ciphertext (crypto.py contract). Connection count is plan-gated
(R-Q5/Q6): free=0, pro=1, team=5 ACTIVE connections; swapping = revoke +
connect.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, Source, Subscription, User, utcnow
from tokenops_cost_auditor.persistence.repo import (
    active_workspace_id,
    get_or_create_user,
    workspace_id_for,
)
from tokenops_cost_auditor.services.connectors import validate
from tokenops_cost_auditor.services.connectors.crypto import (
    credential_fingerprint,
    encrypt_credential,
)
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans
from tokenops_cost_auditor.services.payments.base import unconsumed_credit
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.web import help as help_registry

router = APIRouter(prefix="/sources", tags=["sources"])

log = structlog.get_logger("tokenops_cost_auditor.connectors")

PROVIDERS = ("openai", "anthropic", "azure-openai", "bedrock", "vertex-ai")


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def user_plan(session: Session, user_id: str) -> str:
    # O-1: billing (Subscription) stays user-scoped — see subscriptions.
    # entitlements (PLAN-ORG Q3, deferred to O-1b/O-2). The plan-limit source
    # counts below therefore also stay user-scoped, so both sides of the gate
    # agree; source CREATE/REVOKE are owner-only mutates until O-2 RBAC.
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
        # O-1: the sources page DISPLAYS the workspace's connected sources,
        # machines and SDK keys — a member sees the same connections the owner
        # does. (Creating/revoking a connection stays owner-scoped below —
        # who-may-mutate is O-2 RBAC; the plan-limit count stays user-scoped
        # with billing.)
        ws = active_workspace_id(session, user.id) if user else None
        sources = (
            session.execute(
                select(Source)
                .where(Source.workspace_id == ws, Source.status != "revoked")
                .order_by(Source.created_at)
            )
            .scalars()
            .all()
            if user
            else []
        )
        plan = user_plan(session, user.id) if user else "free"
        active_count = sum(1 for s in sources if s.status == "active")
        from tokenops_cost_auditor.persistence.models import Device, IngestKey

        devices = (
            session.execute(
                select(Device)
                .where(Device.workspace_id == ws, Device.revoked_at.is_(None))
                .order_by(Device.created_at)
            )
            .scalars()
            .all()
            if user
            else []
        )
        ingest_keys = (
            session.execute(
                select(IngestKey)
                .where(IngestKey.workspace_id == ws, IngestKey.revoked_at.is_(None))
                .order_by(IngestKey.created_at)
            )
            .scalars()
            .all()
            if user
            else []
        )
        # Rendered in the APP shell now, not base.html: the designed sidebar
        # links here, so rendering the old shell navigated users out of the
        # product's own design (v4 unify).
        tpl = request.app.state.jinja.get_template("app/sources.html")
        return HTMLResponse(
            tpl.render(
                help=help_registry,
                sources=sources,
                devices=devices,
                ingest_keys=ingest_keys,
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
    api_key: str = Form(""),
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    resource_id: str = Form(""),
    access_key_id: str = Form(""),
    secret_access_key: str = Form(""),
    region: str = Form(""),
    service_account: str = Form(""),
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """Live validation, then save. R-WIZ-DEGRADE: an unreachable provider
    saves the key and says so plainly — it never blocks the customer.

    Azure (WP-CLOUD-T2 C-A) posts four fields instead of one key; they are
    packed into one canonical JSON credential here, so everything downstream
    (fingerprint dedup, encryption, revoke-deletes-all) treats it as the one
    opaque credential it is."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    if provider == "azure-openai":
        fields = {
            "tenant_id": tenant_id.strip(),
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "resource_id": resource_id.strip(),
        }
        if not all(fields.values()):
            raise HTTPException(status_code=400, detail="all four Azure values are required")
        if not fields["resource_id"].startswith("/subscriptions/") or (
            "/providers/Microsoft.CognitiveServices/accounts/" not in fields["resource_id"]
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "that doesn't look like an Azure OpenAI Resource ID — copy it "
                    "from the resource's Properties page (starts /subscriptions/…)"
                ),
            )
        key = json.dumps(fields, sort_keys=True)
    elif provider == "bedrock":
        aws_fields = {
            "access_key_id": access_key_id.strip(),
            "secret_access_key": secret_access_key.strip(),
            "region": region.strip(),
        }
        if not all(aws_fields.values()):
            raise HTTPException(status_code=400, detail="all three AWS values are required")
        from tokenops_cost_auditor.services.connectors import bedrock_usage

        if not bedrock_usage.is_valid_region(aws_fields["region"]):
            raise HTTPException(
                status_code=400,
                detail="that doesn't look like an AWS region — e.g. us-east-1",
            )
        key = json.dumps(aws_fields, sort_keys=True)
    elif provider == "vertex-ai":
        from tokenops_cost_auditor.services.connectors import vertex_usage
        from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

        blob = service_account.strip()
        if not blob:
            raise HTTPException(status_code=400, detail="paste the service-account key JSON")
        try:
            vertex_usage.parse_credential(blob)  # validate shape before storing
        except ConnectorAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # already JSON; store canonically so the fingerprint is stable
        key = json.dumps(json.loads(blob), sort_keys=True)
    else:
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
        # R-MULTI-SOURCE (founder order 2026-07-23): a second ACCOUNT of the
        # same provider is allowed (up to the plan limit) — what is blocked is
        # the SAME key twice, which would pull the same usage into two sources
        # and double-count spend. Also the double-submit guard (f.3).
        fingerprint = credential_fingerprint(settings.secret_key, key)
        dup = next((s for s in active if s.key_fingerprint == fingerprint), None)
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"that key is already connected as “{dup.label}” — "
                    "use a different account's key, or revoke it first"
                ),
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
            if len(still_active) >= limit or any(
                s.key_fingerprint == fingerprint for s in still_active
            ):
                # Someone won the race between our check and this write.
                raise HTTPException(
                    status_code=409, detail=f"{provider} was connected a moment ago"
                )
            # Distinct labels per account — counted over ALL of this user's
            # sources of the provider, revoked included (cold-review f.4:
            # revoke + reconnect must never mint a duplicate label, because
            # /explore keeps revoked accounts selectable by their labels).
            nth = (
                session.execute(
                    select(func.count())
                    .select_from(Source)
                    .where(Source.user_id == user_id, Source.provider == provider)
                ).scalar_one()
                + 1
            )
            source = Source(
                user_id=user_id,
                workspace_id=workspace_id_for(session, user_id),  # O-0
                provider=provider,
                label=f"{provider} usage" if nth == 1 else f"{provider} usage #{nth}",
                credentials_encrypted=encrypt_credential(settings.secret_key, key),
                key_fingerprint=fingerprint,
            )
            session.add(source)
            auditlog.append(session, user_email, "source.connected", provider)
            session.commit()
            saved = True
            source_id = source.id

    free_no_credit = False
    audit_id = None
    if saved and verdict.status == validate.OK:
        # INSTANT GRATIFICATION (R-MAGIC-CONNECT §2): pull and audit NOW, in
        # the background. R-FREE-CONNECT §3: on Free, the first-pull audit is
        # metered by the signup credit — no credit, no audit, said plainly.
        if plan in ("pro", "team"):
            audit_id = _kickoff_first_pull(request, source_id)
        else:
            with _session(request) as session:
                credit = unconsumed_credit(session, user_id)
            if credit is not None:
                audit_id = _kickoff_first_pull(request, source_id, claim_for_user=user_id)
            else:
                free_no_credit = True

    tpl = request.app.state.jinja.get_template("app/_wizard_verdict.html")
    return HTMLResponse(
        tpl.render(
            verdict=verdict,
            copy=help_registry.wizard(provider),
            provider=provider,
            saved=saved,
            free_no_credit=free_no_credit,
            # R-LIVE-AUDIT: when an audit was kicked off, send the customer to the
            # live theater to watch it, not the static dashboard.
            audit_id=audit_id,
        )
    )


def _kickoff_first_pull(
    request: Request, source_id: str, claim_for_user: str | None = None
) -> str | None:
    """Best-effort immediate pull + audit. Failure here NEVER surfaces as a
    connect error — the scheduled tick will do it anyway (paid plans; free
    sources are never scheduled, so a failed free kickoff keeps its credit).

    R-LIVE-AUDIT: a 'queued' Audit row is created SYNCHRONOUSLY and its id is
    returned, so the connect flow can land on the live pipeline theater and the
    customer watches the real pull+audit animate (queued → processing → done),
    instead of a static dashboard that just reads "waiting". Returns None only
    if the source vanished before the row could be created.

    claim_for_user (R-FREE-CONNECT §3): on Free the audit consumes the signup
    credit, claimed atomically once the audit row exists. The window between
    the route's credit check and this claim is microscopic and bounded by the
    provider-idempotency guard on connects; if another spender won the race
    the audit still ran and the account is exactly one audit ahead of its
    meter — accepted and audit-logged, never a customer-facing error."""
    import threading

    settings = request.app.state.settings
    factory = request.app.state.session_factory
    table = request.app.state.pricing_table

    # Create the watchable row up front so the browser has an id to poll.
    with factory() as session:
        source = session.get(Source, source_id)
        if source is None:
            return None
        audit = Audit(
            user_id=source.user_id,
            status="queued",
            paid_via="subscription",
            source_id=source.id,  # R-MULTI-SOURCE: per-account attribution
        )
        session.add(audit)
        session.commit()
        audit_id = audit.id

    threading.Thread(
        target=_process_first_pull,
        args=(factory, settings, table, source_id, audit_id, claim_for_user),
        daemon=True,
    ).start()
    return audit_id


def _mark_failed(session: Session, audit_id: str, why: str) -> None:
    """Give the live theater a terminal state so it stops polling a stuck row."""
    row = session.get(Audit, audit_id)
    if row is not None and row.status in ("queued", "processing"):
        row.status = "failed"
        row.error = why
        session.commit()


def _process_first_pull(
    factory: Callable[[], Session],
    settings: Settings,
    table: PricingTable,
    source_id: str,
    audit_id: str,
    claim_for_user: str | None,
) -> None:
    """The connect first-pull worker (runs in a daemon thread; extracted to a
    module-level function so the lifecycle is unit-testable). Drives the
    pre-created 'queued' Audit row through processing → done, or to 'failed' on
    any error / vanished source, so the theater always reaches a terminal state
    (R-LIVE-AUDIT, cold-review f.2)."""
    from tokenops_cost_auditor.services.connectors.pull import record_pull_failure, run_pull
    from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit
    from tokenops_cost_auditor.services.payments.base import claim_credit

    pull_ok = False  # only a failure BEFORE this flips is a pull failure
    try:
        with factory() as session:
            source = session.get(Source, source_id)
            row = session.get(Audit, audit_id)
            if source is None or row is None:
                if row is not None:
                    _mark_failed(
                        session,
                        audit_id,
                        "The connection was removed before its first audit ran.",
                    )
                return
            row.status = "processing"  # the theater lights up while we pull
            session.commit()
            run_pull(session, settings, source)
            session.commit()
            pull_ok = True
            run_source_audit(session, settings, table, source, audit=row)
            if claim_for_user is not None:
                claimed = claim_credit(session, claim_for_user, audit_id)
                if claimed is None:
                    log.info("connect.free_credit_race", audit_id=audit_id)
            session.commit()
    except Exception as exc:
        log.info("connect.first_pull_deferred", error=str(exc)[:160])
        try:
            with factory() as session:
                _mark_failed(
                    session,
                    audit_id,
                    "We couldn't finish this first audit. We'll retry automatically.",
                )
                if not pull_ok:  # audit-step failures are not pull failures
                    record_pull_failure(session, source_id, exc)
        except Exception:  # failure-marking is best-effort; never re-raise
            pass


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
    if provider in ("azure-openai", "bedrock", "vertex-ai"):
        # The plain POST path must carry the SAME packed JSON the wizard
        # produces — a bare key here would fail every later pull.
        from tokenops_cost_auditor.services.connectors import (
            azure_usage,
            bedrock_usage,
            vertex_usage,
        )
        from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

        parser = {
            "azure-openai": azure_usage.parse_credential,
            "bedrock": bedrock_usage.parse_credential,
            "vertex-ai": vertex_usage.parse_credential,
        }[provider]
        try:
            parser(api_key)
        except ConnectorAuthError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{provider} needs its packed credential fields — use the "
                    f"guided connect at /sources/connect/{provider}"
                ),
            ) from None
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
        # R-MULTI-SOURCE: same key twice = double-counted usage; block with the
        # existing connection named. A different account of the same provider
        # is fine.
        fingerprint = credential_fingerprint(settings.secret_key, api_key.strip())
        dup = next((s for s in active if s.key_fingerprint == fingerprint), None)
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"that key is already connected as “{dup.label}” — "
                    "use a different account's key, or revoke it first"
                ),
            )
        session.add(
            Source(
                user_id=user.id,
                workspace_id=workspace_id_for(session, user.id),  # O-0
                provider=provider,
                label=label.strip()[:120] or provider,
                credentials_encrypted=encrypt_credential(settings.secret_key, api_key.strip()),
                key_fingerprint=fingerprint,
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
        # O-1: revoke is a MUTATE — stays owner-scoped (fail-closed until O-2
        # RBAC). Members SEE the workspace's sources but cannot revoke them yet.
        source = session.get(Source, source_id)
        if source is None or source.user_id != user.id:
            raise HTTPException(status_code=404, detail="source not found")
        source.status = "revoked"
        source.credentials_encrypted = None  # ciphertext deleted, not just flagged
        source.revoked_at = utcnow()
        auditlog.append(session, user.email, "source.revoked", source.provider)
        session.commit()
    return RedirectResponse("/sources", status_code=303)
