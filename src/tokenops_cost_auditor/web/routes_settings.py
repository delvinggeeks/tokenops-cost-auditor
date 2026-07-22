"""Settings (PLAN-V15 V-D7 / WP-5). Boring on purpose (R-DESIGN §4f):
one grouped page, inline saves, destructive actions double-confirmed with
the consequence stated in words rather than a scary colour.

Sources add/revoke lives here too (founder, 2026-07-22) — the same routes
that back /sources, not a second implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import Audit, Source, Subscription, utcnow
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog, purge
from tokenops_cost_auditor.services.payments import subscriptions
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
        session.commit()
        sources = (
            session.execute(
                select(Source)
                .where(Source.user_id == user.id, Source.status != "revoked")
                .order_by(Source.created_at)
            )
            .scalars()
            .all()
        )
        held = (
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
        plan = user_plan(session, user.id)
        ctx = _shell_ctx(session, request, user, "settings")
        return _render(
            request,
            "app/settings.html",
            sources=sources,
            providers=PROVIDERS,
            plan=plan_display(plan, settings),
            plan_key=plan,
            source_limit=settings.plan_source_limits.get(plan, 0),
            statement_emails=user.statement_emails is not False,
            daily_digest_emails=user.daily_digest_emails is not False,
            held_uploads=len(held),
            retention_days=settings.purge_after_days,
            purge_phrase=PURGE_PHRASE,
            close_phrase=CLOSE_PHRASE,
            purged=purged,
            closed=closed,
            show_tour=False,
            **{k: v for k, v in ctx.items() if k != "plan"},
        )


def plan_display(plan: str, settings: object) -> str:
    """Display name comes from THE catalogue — str.title() on the internal
    key resurrected "Team" after the R-SAAS-BASICS rename."""
    from tokenops_cost_auditor.services.payments import plans as catalogue

    p = catalogue.get(settings, plan)  # type: ignore[arg-type]
    return f"{p.name} — ${p.usd:,.0f}/mo" if p.usd else p.name


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
