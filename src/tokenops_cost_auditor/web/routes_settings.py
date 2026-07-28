"""Settings (PLAN-V15 V-D7 / WP-5). Boring on purpose (R-DESIGN §4f):
one grouped page, inline saves, destructive actions double-confirmed with
the consequence stated in words rather than a scary colour.

Sources add/revoke lives here too (founder, 2026-07-22) — the same routes
that back /sources, not a second implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import Audit, Source, Subscription, utcnow
from tokenops_cost_auditor.persistence.repo import (
    active_role,
    active_workspace_id,
    get_or_create_user,
    get_or_create_workspace,
    list_workspace_audit_log,
    set_active_workspace,
)
from tokenops_cost_auditor.services.lifecycle import auditlog, purge
from tokenops_cost_auditor.services.payments import subscriptions
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.auth import SESSION_COOKIE
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx
from tokenops_cost_auditor.web.routes_sources import PROVIDERS, user_plan

router = APIRouter(prefix="/settings", tags=["settings"])

# Typed exactly, because it destroys data (R-DESIGN §4f double-confirm)
PURGE_PHRASE = "DELETE MY UPLOADS"
# R-SAAS-BASICS 4a — closing an account outranks purging uploads, so it gets
# its own phrase, never a shared one.
CLOSE_PHRASE = "CLOSE MY ACCOUNT"


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request,
    purged: int | None = None,
    closed: int | None = None,
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        workspace = get_or_create_workspace(session, user)  # O-0: the tenancy root
        session.commit()
        ws = active_workspace_id(session, user.id)
        sources = (
            session.execute(
                select(Source)
                .where(Source.workspace_id == ws, Source.status != "revoked")
                .order_by(Source.created_at)
            )
            .scalars()
            .all()
        )
        held = (
            session.execute(
                select(Audit).where(
                    Audit.workspace_id == ws,
                    Audit.upload_path.is_not(None),
                    Audit.purged_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        plan = user_plan(session, user.id)
        ctx = _shell_ctx(session, request, user, "settings")
        return _render(
            request,
            "app/settings.html",
            sources=sources,
            providers=PROVIDERS,
            workspace_name=workspace.name,
            workspace_personal=workspace.personal,
            plan=plan_display(plan, settings),
            plan_key=plan,
            source_limit=settings.plan_source_limits.get(plan, 0),
            statement_emails=user.statement_emails is not False,
            daily_digest_emails=user.daily_digest_emails is not False,
            benchmark_sharing=user.benchmark_sharing is not False,
            cohort_opt_in=workspace.cohort_opt_in,
            held_uploads=len(held),
            retention_days=settings.purge_after_days,
            purge_phrase=PURGE_PHRASE,
            close_phrase=CLOSE_PHRASE,
            purged=purged,
            closed=closed,
            show_tour=False,
            settings_tab="general",  # O-4 settings-home tab spine
            **{k: v for k, v in ctx.items() if k != "plan"},
        )


@router.get("/sign-in", response_class=HTMLResponse)
def sign_in_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """O-4 Sign-in tab: how you reach this account. The email magic-link always works;
    plus any federated methods the deployment has configured (Google/Microsoft/GitHub).
    Federation is login-ONLY — there is no per-user 'connected' record — so we show the
    AVAILABLE methods honestly, never a fake 'connected' badge or a dead control."""
    from tokenops_cost_auditor.web.routes_auth import enabled_federations

    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ctx = _shell_ctx(session, request, user, "settings")
    return _render(
        request,
        "app/settings_signin.html",
        federations=enabled_federations(request.app.state.settings),
        settings_tab="signin",
        **{k: v for k, v in ctx.items() if k != "plan"},  # ctx supplies user_email
    )


@router.get("/audit-log", response_class=HTMLResponse)
def audit_log_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """O-4 Audit-log tab: the workspace governance trail — who did what. Surfaces the
    existing append-only AuditLogEntry, scoped to the active workspace's members (the
    log has no workspace_id; see repo.list_workspace_audit_log). Counts/metadata only
    (FR-22): the log never held prompt or completion text."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ws = active_workspace_id(session, user.id)
        assert ws is not None
        entries = [
            {
                "ts": e.ts,
                "actor": e.actor,
                "action": e.action.replace(".", " ").replace("_", " "),
                "subject": e.subject,
            }
            for e in list_workspace_audit_log(session, ws)
        ]
        ctx = _shell_ctx(session, request, user, "settings")
    return _render(
        request,
        "app/settings_audit_log.html",
        entries=entries,
        settings_tab="auditlog",
        **{k: v for k, v in ctx.items() if k != "plan"},
    )


def plan_display(plan: str, settings: object) -> str:
    """Display name comes from THE catalogue — str.title() on the internal
    key resurrected "Team" after the R-SAAS-BASICS rename."""
    from tokenops_cost_auditor.services.payments import plans as catalogue

    p = catalogue.get(settings, plan)  # type: ignore[arg-type]
    return f"{p.name} — ${p.usd:,.0f}/mo" if p.usd else p.name


@router.post("/benchmarks", response_model=None)
def save_benchmark_pref(
    request: Request,
    benchmark_sharing: str | None = Form(default=None),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """R-F1 SIGN-OFF: cohort membership is the customer's call, one checkbox.
    Audit-logged — leaving or rejoining the benchmark cohort is a data-use
    decision, and data-use decisions leave a trail here."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        user.benchmark_sharing = benchmark_sharing is not None
        auditlog.append(
            session,
            user.email,
            "settings.benchmark_sharing",
            "included" if benchmark_sharing is not None else "excluded",
        )
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/workspace/rename", response_model=None)
def rename_workspace(
    request: Request,
    name: str = Form(""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """O-0 (R-ORG): the owner renames their workspace. Only an owner may rename;
    in O-0 every user owns their workspace-of-one. Audit-logged."""
    new_name = name.strip()[:80]
    if not new_name:
        raise HTTPException(status_code=400, detail="give your workspace a name")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        workspace = get_or_create_workspace(session, user)
        workspace.name = new_name
        auditlog.append(session, user.email, "workspace.renamed", new_name)
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/workspace/cohort-opt-in", response_model=None)
def save_cohort_opt_in(
    request: Request,
    cohort_opt_in: str | None = Form(default=None),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """FR-35 (R-MODEL-FACTORY): the workspace's consent to the cohort export —
    the ONLY data path into the model factory. Owner-only (MANAGE_WORKSPACE,
    data-use governance is an owner act); the page hides the toggle from every
    other role AND the route refuses a forged POST (defense in depth,
    authorized BEFORE commit — the routes_dashboard showback idiom). Every
    flip is audit-logged, same as settings.benchmark_sharing."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        workspace = get_or_create_workspace(session, user)
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_WORKSPACE,
            detail="only the workspace owner can change the cohort export setting",
        )
        workspace.cohort_opt_in = cohort_opt_in is not None
        auditlog.append(
            session,
            user.email,
            "settings.cohort_opt_in",
            "opted_in" if cohort_opt_in is not None else "opted_out",
        )
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/workspace/switch", response_model=None)
def switch_workspace(
    request: Request,
    workspace_id: str = Form(""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """O-1b-1 (R-ORG): move the user into another workspace they belong to.

    `set_active_workspace` refuses and changes nothing unless the user is a live
    member of the target (the switch can NEVER become a privilege grant, and a
    forged/foreign workspace_id silently no-ops — the switcher only ever lists
    workspaces the user belongs to). Every owned read then re-scopes to the new
    active workspace via `active_workspace_id`. Audit-logged when it takes."""
    target = workspace_id.strip()
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # Only switch (and audit) on a REAL change to a workspace the user
        # belongs to — a self-switch or empty/foreign target writes nothing and
        # logs nothing, keeping the audit trail to genuine moves.
        if (
            target
            and target != active_workspace_id(session, user.id)
            and set_active_workspace(session, user.id, target)
        ):
            auditlog.append(session, user.email, "workspace.switched", target)
        session.commit()
    # land on the dashboard so the switch is immediately visible (every widget
    # now reads the new workspace's data) — the journey's proof, in one hop.
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/email", response_model=None)
def save_email_prefs(
    request: Request,
    statement_emails: str | None = Form(default=None),
    daily_digest_emails: str | None = Form(default=None),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        user.statement_emails = statement_emails is not None
        user.daily_digest_emails = daily_digest_emails is not None
        auditlog.append(session, user.email, "settings.email_prefs", user.email)
        session.commit()
    return RedirectResponse("/settings", status_code=303)


@router.post("/purge", response_model=None)
def purge_now(
    request: Request,
    confirm: str = Form(default=""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """Delete every raw upload we still hold for this account, now.

    Derived aggregates (counts only, FR-22) and rendered reports survive —
    the page says so in words before the customer types the phrase, because
    a data-deletion control that surprises you is a broken one.
    """
    if confirm.strip() != PURGE_PHRASE:
        return RedirectResponse("/settings?purged=-1", status_code=303)
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-1: DESTRUCTIVE mutate — stays user-scoped. Flipping this to workspace
        # would let one member purge every member's uploads (data-loss bug); who
        # may purge a workspace's data is an O-2 RBAC decision. Fail-closed.
        audits = (
            session.execute(
                select(Audit).where(
                    Audit.user_id == user.id,
                    Audit.upload_path.is_not(None),
                    Audit.purged_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        count = sum(
            1
            for audit in audits
            # ONE purge definition, shared with the scheduled and admin paths
            if purge.purge_one(session, audit, actor=user.email, mode="customer")
        )
        auditlog.append(session, user.email, "settings.purge_now", user.email, {"count": count})
        session.commit()
    return RedirectResponse(f"/settings?purged={count}", status_code=303)


@router.post("/close-account", response_model=None)
def close_account(
    request: Request,
    confirm: str = Form(default=""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """R-SAAS-BASICS 4a. Everything stated on the page happens, in order:
    raw uploads purged (ONE purge definition), connected keys revoked and
    their ciphertext deleted, the subscription cancelled on our side, this
    session ended — all audit-logged.

    Provider-side subscription closure: the payment adapters are link+webhook
    only (no provider API credential exists in this system), so the provider
    record is closed manually within 1 business day; the audit-log entry and
    the daily digest carry the task to the founder. The page says exactly
    this — a promise the code cannot keep never ships as copy.
    """
    if confirm.strip() != CLOSE_PHRASE:
        return RedirectResponse("/settings?closed=-1", status_code=303)
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-1: "close MY account" is inherently per-user — it purges the caller's
        # own uploads, revokes the caller's own sources, cancels the caller's own
        # subscription. These STAY user-scoped by construction; scoping them to
        # the workspace would destroy other members' data when one member leaves.
        audits = (
            session.execute(
                select(Audit).where(
                    Audit.user_id == user.id,
                    Audit.upload_path.is_not(None),
                    Audit.purged_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        purged = sum(
            1
            for audit in audits
            if purge.purge_one(session, audit, actor=user.email, mode="customer")
        )
        # keys must not outlive the decision to leave
        sources = (
            session.execute(
                select(Source).where(Source.user_id == user.id, Source.status != "revoked")
            )
            .scalars()
            .all()
        )
        for source in sources:
            source.status = "revoked"
            source.credentials_encrypted = None
            source.revoked_at = utcnow()
        sub = session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        had_paid_sub = bool(sub and sub.status != subscriptions.CANCELLED)
        if had_paid_sub and sub is not None:
            sub.status = subscriptions.CANCELLED
        # Real session kill (readiness audit 2026-07-22): stateless signed
        # cookies can't be deleted server-side, so we bump the session epoch —
        # every cookie issued before now is now rejected, on every device.
        user.sessions_valid_from = utcnow()
        auditlog.append(
            session,
            user.email,
            "account.closed",
            user.email,
            {
                "purged": purged,
                "sources_revoked": len(sources),
                # the founder's manual task, carried by log + daily digest
                "provider_cancellation_required": had_paid_sub,
            },
        )
        session.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
