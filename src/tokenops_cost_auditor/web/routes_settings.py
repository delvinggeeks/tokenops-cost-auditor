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
from tokenops_cost_auditor.persistence.models import Audit, Source
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog, purge
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx
from tokenops_cost_auditor.web.routes_sources import PROVIDERS, user_plan

router = APIRouter(prefix="/settings", tags=["settings"])

# Typed exactly, because it destroys data (R-DESIGN §4f double-confirm)
PURGE_PHRASE = "DELETE MY UPLOADS"


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request, purged: int | None = None, user_email: str = Depends(current_user)
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
            held_uploads=len(held),
            retention_days=settings.purge_after_days,
            purge_phrase=PURGE_PHRASE,
            purged=purged,
            show_tour=False,
            **{k: v for k, v in ctx.items() if k != "plan"},
        )


def plan_display(plan: str, settings: object) -> str:
    prices = {
        "pro": f"${getattr(settings, 'plan_pro_usd', 99):,.0f}/mo",
        "team": f"${getattr(settings, 'plan_team_usd', 299):,.0f}/mo",
    }
    return f"{plan.title()} — {prices[plan]}" if plan in prices else plan.title()


@router.post("/email", response_model=None)
def save_email_prefs(
    request: Request,
    statement_emails: str | None = Form(default=None),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        user.statement_emails = statement_emails is not None
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
