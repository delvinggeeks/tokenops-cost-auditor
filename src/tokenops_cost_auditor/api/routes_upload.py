"""Audit upload + status API (FR-01 API side, FR-17/18 enforcement, FR-25/FR-26,
NFR-03/10/12/13).

All routes live under /api/v1 (FR-25). Auth (FR-17): the magic-link session
cookie identifies the caller; outside prod the X-User-Email header remains as a
development/test shim. Payment gate (FR-18): one paid credit is consumed per
audit; without a credit the upload is refused with 402 and the configured
payment link(s).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import IdempotencyKey
from tokenops_cost_auditor.persistence.repo import (
    create_audit as repo_create_audit,
)
from tokenops_cost_auditor.persistence.repo import (
    find_idempotent_audit,
    get_or_create_user,
    get_user_audit,
    queue_position,
)
from tokenops_cost_auditor.services.ingest.base import ALLOWED_EXTENSIONS, IngestError, check_file
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments.base import claim_credit, unconsumed_credit
from tokenops_cost_auditor.web.auth import resolve_session

router = APIRouter(prefix="/api/v1", tags=["audits"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHUNK = 1024 * 1024


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def current_user(request: Request, x_user_email: str | None = Header(default=None)) -> str:
    """FR-17: magic-link session cookie wins; X-User-Email is a NON-PROD dev/test
    shim only (refused in prod)."""
    settings: Settings = request.app.state.settings
    email = resolve_session(request, settings.secret_key, settings.session_ttl_days)
    if email:
        request.state.user_email = email  # NFR-12 rate-limit key
        return email
    if settings.app_env != "prod" and x_user_email and EMAIL_RE.match(x_user_email):
        request.state.user_email = x_user_email.lower()
        return x_user_email.lower()
    raise HTTPException(status_code=401, detail="authentication required")


def payment_gate(request: Request, user_email: str = Depends(current_user)) -> str:
    """FR-18: an unconsumed paid credit must exist before upload; 402 otherwise.
    The credit itself is consumed atomically at audit creation."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        credit = unconsumed_credit(session, user.id)
        session.commit()
    if credit is None:
        links = {
            "razorpay_inr": request.app.state.razorpay.payment_link(),
            "stripe_usd": request.app.state.stripe.payment_link(),
        }
        detail = "payment required before upload — pay via the provided link, then retry"
        raise HTTPException(status_code=402, detail=f"{detail}; links: {links}")
    return user_email


@router.post("/audits", status_code=201, response_model=None)
@limiter.limit("10/minute")
def create_audit(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
    user_email: str = Depends(payment_gate),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        if idempotency_key:  # FR-26
            existing = find_idempotent_audit(session, user.id, idempotency_key)
            if existing is not None:
                session.commit()
                return JSONResponse(
                    status_code=200, content={"audit_id": existing.id, "replayed": True}
                )

        suffix = Path(file.filename or "upload.jsonl").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported file extension '{suffix}' — accepted: "
                + ", ".join(ALLOWED_EXTENSIONS),
            )

        audit = repo_create_audit(session, user.id)
        # atomic claim: UPDATE-where-unclaimed, rowcount-checked — two concurrent
        # uploads cannot double-spend one credit (G5 cold-reviewer f.1). On None
        # the raised 402 discards this uncommitted session (audit never persists).
        credit = claim_credit(session, user.id, audit.id)
        if credit is None:
            raise HTTPException(status_code=402, detail="payment required before upload")
        audit.paid_via = credit.provider
        upload_dir = Path(settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"original{suffix}"
        max_bytes = settings.max_upload_mb * 1024 * 1024
        written = 0
        with dest.open("wb") as out:
            while chunk := file.file.read(CHUNK):
                written += len(chunk)
                if written > max_bytes:  # FR-01 cap enforced while streaming
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds the {settings.max_upload_mb}MB upload limit",
                    )
                out.write(chunk)
        try:
            check_file(dest, settings.max_upload_mb)  # emptiness + extension re-check
        except IngestError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        audit.upload_path = str(dest)
        if idempotency_key:
            session.add(IdempotencyKey(user_id=user.id, key=idempotency_key, audit_id=audit.id))
        auditlog.append(session, user_email, "audit.uploaded", audit.id)
        session.commit()
        audit_id = audit.id

    background.add_task(request.app.state.runner.run, audit_id)
    # A browser form post landed on raw JSON until the pipeline theater
    # (R-PIPELINE-UI-SEQ carve-out i). Browsers lead Accept with text/html;
    # API clients don't — the JSON contract is unchanged for them.
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(f"/audits/{audit_id}/progress", status_code=303)
    return JSONResponse(status_code=201, content={"audit_id": audit_id, "replayed": False})


@router.get("/audits/{audit_id}/status")
def audit_status(
    request: Request, audit_id: str, user_email: str = Depends(current_user)
) -> dict[str, object]:
    with _session(request) as session:
        audit = get_user_audit(session, audit_id, user_email)
        if audit is None:
            raise HTTPException(status_code=404, detail="audit not found")
        body: dict[str, object] = {"audit_id": audit.id, "status": audit.status}
        if audit.valid_pct is not None:
            body["valid_pct"] = audit.valid_pct
        if audit.error:
            body["error"] = audit.error
        if audit.status == "queued":
            body["queue_position"] = queue_position(session, audit)  # NFR-13
        return body
