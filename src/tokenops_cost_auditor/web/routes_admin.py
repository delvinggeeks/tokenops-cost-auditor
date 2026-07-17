"""Admin panel (FR-19): X-Admin-Token gated, IP-logged, every action in the
append-only audit_log. Paths per docs/03 §5 (/admin — web layer, not /api/v1)."""

from __future__ import annotations

import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Audit, User
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments.base import grant_payment

router = APIRouter(prefix="/admin", tags=["admin"])


def admin_actor(request: Request) -> str:
    """Token gate (HLD §6): 404 when unset/wrong — the panel does not exist."""
    settings = request.app.state.settings
    supplied = request.headers.get("X-Admin-Token", "")
    if not settings.admin_token or not secrets.compare_digest(supplied, settings.admin_token):
        raise HTTPException(status_code=404, detail="not found")
    client = request.client.host if request.client else "unknown"
    return f"admin@{client}"  # IP-logged actor for audit_log


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, actor: str = Depends(admin_actor)) -> HTMLResponse:
    with _session(request) as session:
        audits = session.execute(
            select(Audit, User.email)
            .join(User, Audit.user_id == User.id)
            .order_by(Audit.created_at.desc())
            .limit(200)
        ).all()
        rows = "".join(
            f"<tr><td><code>{a.id}</code></td><td>{email}</td><td>{a.status}</td>"
            f"<td>{a.paid_via or '-'}</td><td>{a.created_at:%Y-%m-%d %H:%M}</td>"
            f"<td>{'purged' if a.purged_at else '-'}</td></tr>"
            for a, email in audits
        )
    return HTMLResponse(
        "<h1>TokenOps Cost Auditor — admin</h1>"
        "<p>Actions: POST /admin/audits/{id}/rerun · POST /admin/audits/{id}/purge · "
        "POST /admin/payments/mark-paid (email, amount, currency, provider)</p>"
        f"<table border=1 cellpadding=4><tr><th>audit</th><th>user</th><th>status</th>"
        f"<th>paid via</th><th>created</th><th>purge</th></tr>{rows}</table>"
    )


@router.post("/audits/{audit_id}/rerun")
def rerun_audit(
    request: Request,
    audit_id: str,
    background: BackgroundTasks,
    actor: str = Depends(admin_actor),
) -> dict[str, str]:
    with _session(request) as session:
        audit = session.get(Audit, audit_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="audit not found")
        if audit.purged_at is not None or not audit.upload_path:
            raise HTTPException(status_code=400, detail="upload purged — cannot re-run")
        audit.status = "queued"
        audit.error = None
        auditlog.append(session, actor, "audit.rerun_requested", audit_id)
        session.commit()
    background.add_task(request.app.state.runner.run, audit_id)
    return {"status": "queued", "audit_id": audit_id}


@router.post("/audits/{audit_id}/purge")
def purge_audit(
    request: Request, audit_id: str, actor: str = Depends(admin_actor)
) -> dict[str, str]:
    """Manual purge (FR-19/FR-21): removes the raw upload, keeps derived data."""
    with _session(request) as session:
        audit = session.get(Audit, audit_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="audit not found")
        if audit.upload_path:
            shutil.rmtree(Path(audit.upload_path).parent, ignore_errors=True)
        audit.upload_path = None
        audit.purged_at = datetime.now(UTC)
        auditlog.append(session, actor, "audit.purged", audit_id, {"mode": "manual"})
        session.commit()
    return {"status": "purged", "audit_id": audit_id}


@router.post("/payments/mark-paid")
def mark_paid(
    request: Request,
    actor: str = Depends(admin_actor),
    email: str = Form(...),
    amount: float = Form(0.0),
    currency: str = Form("USD"),
    provider: str = Form("manual"),
) -> dict[str, str]:
    """FR-18 manual fulfillment; comp grants use provider='comp', amount 0 (Q8)."""
    if provider not in ("manual", "comp", "razorpay", "stripe"):
        raise HTTPException(status_code=400, detail="unknown provider")
    with _session(request) as session:
        user = get_or_create_user(session, email)
        payment = grant_payment(session, user.id, provider, amount, currency)
        auditlog.append(
            session,
            actor,
            "payment.marked_paid",
            user.email,
            {"payment_id": payment.id, "provider": provider, "amount": amount},
        )
        session.commit()
    return {"status": "paid", "email": email.lower()}
