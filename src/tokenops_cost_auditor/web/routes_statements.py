"""Savings Statements (PLAN-V15 V-D6 / WP-4): list, read, resend.

The statement is the OWNER artifact — designed to be forwarded to someone
who never logs in here. This page just makes it reachable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import Statement
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.statements import build as statements
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

router = APIRouter(prefix="/statements", tags=["statements"])


@router.get("", response_class=HTMLResponse)
def statements_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        rows = (
            session.execute(
                select(Statement)
                .where(Statement.user_id == user.id)
                .order_by(Statement.period.desc())
            )
            .scalars()
            .all()
        )
        # A preview of the current month, so the page is never empty and the
        # owner can see the artifact before it is ever sent.
        now = datetime.now(UTC)
        preview = statements.build(session, user, now.year, now.month)
        ctx = _shell_ctx(session, request, user, "statements")
        return _render(
            request,
            "app/statements.html",
            rows=rows,
            preview=preview,
            show_tour=False,
            **ctx,
        )


@router.get("/{period}", response_class=HTMLResponse)
def statement_detail(
    request: Request, period: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        row = session.execute(
            select(Statement).where(Statement.user_id == user.id, Statement.period == period)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="statement not found")
        ctx = _shell_ctx(session, request, user, "statements")
        return _render(request, "app/statement_detail.html", row=row, show_tour=False, **ctx)


@router.post("/{period}/send", response_model=None)
def send_statement(
    request: Request, period: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    """Issue it, or re-send an already-issued one to the same address."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        row = session.execute(
            select(Statement).where(Statement.user_id == user.id, Statement.period == period)
        ).scalar_one_or_none()
        if row is None:
            year, month = int(period[:4]), int(period[5:7])
            doc = statements.build(session, user, year, month)
            row = statements.archive(session, user, doc)
            session.flush()
        first_send = statements.send(session, request.app.state.mail, user, row)
        if not first_send:
            # already issued: deliver the archived artifact again, unchanged
            deliver = getattr(request.app.state.mail, "alert", None)
            if callable(deliver):
                deliver(
                    user.email, row.subject or f"AI spend statement {row.period}", row.body_text
                )
        auditlog.append(session, user.email, "statement.sent", row.period)
        session.commit()
    return RedirectResponse(f"/statements/{period}", status_code=303)
