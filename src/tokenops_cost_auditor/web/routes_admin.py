"""Admin panel (FR-19): X-Admin-Token gated, IP-logged, every action in the
append-only audit_log. Paths per docs/03 §5 (/admin — web layer, not /api/v1)."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Audit, Subscription, User
from tokenops_cost_auditor.persistence.repo import get_or_create_user, workspace_id_for
from tokenops_cost_auditor.services.lifecycle import auditlog, purge
from tokenops_cost_auditor.services.payments.base import grant_payment

router = APIRouter(prefix="/admin", tags=["admin"])


def admin_actor(request: Request) -> str:
    """Token gate (HLD §6): 404 when unset/wrong — the panel does not exist."""
    settings = request.app.state.settings
    supplied = request.headers.get("X-Admin-Token", "")
    if not settings.admin_token or not secrets.compare_digest(supplied, settings.admin_token):
        raise HTTPException(status_code=404, detail="not found")
    # behind Caddy the peer address is the proxy; XFF carries the client
    # (spoofable only when NOT behind the proxy — acceptable for audit logging)
    forwarded = request.headers.get("X-Forwarded-For", "")
    client = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
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
    try:
        with _session(request) as session:
            from tokenops_cost_auditor.services.flywheel import cohort

            flywheel_line = cohort.status(session, request.app.state.settings).digest_line()
    except Exception:  # cold-review f.2: a flywheel bug must never 500 the
        flywheel_line = "Flywheel: unavailable (check logs)"  # founder's ops panel
    # T-F2 · FR-35: cohort-export state beside the flywheel digest. Below the
    # k-floor the refusal IS the surface (no download exists to offer); the
    # founder-facing count is allowed here — customer surfaces never count down.
    try:
        with _session(request) as session:
            from tokenops_cost_auditor.services.flywheel import export as cohort_export

            settings = request.app.state.settings
            exp = cohort_export.build(
                session, settings, settings.secret_key, cohort_export.current_period()
            )
        if exp.live:
            export_line = (
                f"Cohort export: period {exp.period} · live — {exp.k} opted-in "
                f"workspace(s) · GET /admin/cohort-export.json"
            )
        else:
            export_line = f"Cohort export: period {exp.period} · {exp.reason}"
    except Exception:  # same law as the digest: never 500 the ops panel
        export_line = "Cohort export: unavailable (check logs)"
    return HTMLResponse(
        "<h1>TokenOps Cost Auditor — admin</h1>"
        f"<p>{flywheel_line}</p>"
        f"<p>{export_line}</p>"
        "<p>Actions: POST /admin/audits/{id}/rerun · POST /admin/audits/{id}/purge · "
        "GET /admin/audits/{id}/report · GET /admin/cohort-export.json · "
        "POST /admin/payments/mark-paid (email, amount, currency, provider)</p>"
        f"<table border=1 cellpadding=4><tr><th>audit</th><th>user</th><th>status</th>"
        f"<th>paid via</th><th>created</th><th>purge</th></tr>{rows}</table>"
    )


@router.post("/plans/grant")
def grant_plan(
    request: Request,
    email: str = Form(...),
    plan: str = Form(...),
    actor: str = Depends(admin_actor),
) -> dict[str, str]:
    """Founder ops (R-DOGFOOD 2026-07-23): grant/set an account's plan without
    touching the database by hand — the direct-SQL path is exactly what an
    audit product must never need. provider='manual' marks it as an ops
    grant, audit-logged with the actor; setting plan='free' removes the
    manual subscription (reverts to the real state)."""
    from tokenops_cost_auditor.services.payments import plans as catalogue

    valid = set(catalogue.catalogue(request.app.state.settings))
    if plan not in valid:
        raise HTTPException(status_code=400, detail=f"unknown plan (one of {sorted(valid)})")
    with _session(request) as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="no such account")
        sub = session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        ).scalar_one_or_none()
        if plan == "free":
            if sub is not None and sub.provider == "manual":
                session.delete(sub)
            elif sub is not None:
                raise HTTPException(
                    status_code=400,
                    detail="account has a REAL subscription — cancel via the provider, not here",
                )
        elif sub is None:
            session.add(
                Subscription(
                    user_id=user.id,
                    workspace_id=workspace_id_for(session, user.id),  # O-0
                    provider="manual",
                    plan=plan,
                    status="active",
                )
            )
        elif sub.provider == "manual":
            sub.plan = plan
            sub.status = "active"
        else:
            raise HTTPException(
                status_code=400,
                detail="account has a REAL subscription — plan changes go through billing",
            )
        auditlog.append(session, actor, "plan.granted", email, {"plan": plan})
        session.commit()
    return {"ok": "granted", "email": email, "plan": plan}


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
        purge.purge_one(session, audit, actor=actor, mode="manual")
        session.commit()
    return {"status": "purged", "audit_id": audit_id}


@router.get("/audits/{audit_id}/report", response_model=None)
def download_report(
    request: Request, audit_id: str, actor: str = Depends(admin_actor)
) -> FileResponse:
    """FR-19 download report: the rendered PDF, without minting a signed URL."""
    with _session(request) as session:
        audit = session.get(Audit, audit_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="audit not found")
        pdf_path = Path(request.app.state.settings.report_dir) / audit_id / "report.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="report not rendered")
        auditlog.append(session, actor, "report.admin_downloaded", audit_id)
        session.commit()
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"tokenops-cost-audit-{audit_id[:8]}.pdf",
    )


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
    if amount < 0:  # G5 cold-reviewer f.5: a negative credit must not unlock uploads
        raise HTTPException(status_code=400, detail="amount must be >= 0")
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


@router.get("/cohort-export.json", response_model=None)
def cohort_export_download(
    request: Request,
    period: str | None = None,
    actor: str = Depends(admin_actor),
) -> JSONResponse:
    """T-F2 · FR-35: the factory's ONLY inlet — aggregate envelopes, tenancy
    already stripped by the exporter. Below the k-anonymity floor → honest 404
    whose detail names n and the floor (FR-35 "exports nothing and says why"),
    never an empty-but-valid file. Every pull lands in the audit log — data
    leaving the platform leaves a trail."""
    from tokenops_cost_auditor.services.flywheel import export as cohort_export

    settings = request.app.state.settings
    which = period or cohort_export.current_period()
    with _session(request) as session:
        exp = cohort_export.build(session, settings, settings.secret_key, which)
        if not exp.live:
            raise HTTPException(status_code=404, detail=exp.reason)
        auditlog.append(session, actor, "cohort_export.pulled", exp.period, {"k": exp.k})
        session.commit()
    return JSONResponse(
        exp.to_dict(),
        headers={"Content-Disposition": f"attachment; filename=cohort-export-{exp.period}.json"},
    )
