"""Audit upload + status API (FR-01 API side, FR-25/FR-26, NFR-03/10/12/13).

All routes live under /api/v1 (FR-25). Auth: pre-D8 stub — the X-User-Email
header identifies the caller outside prod (replaced by session-cookie auth at
D8; see PLAN WP-D8). Payment gate: pre-D9 stub allows all (FR-18 enforcement
lands at D9 behind the same dependency).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import Audit, IdempotencyKey, User
from tokenops_cost_auditor.persistence.repo import (
    find_idempotent_audit,
    get_or_create_user,
    queue_position,
)
from tokenops_cost_auditor.services.ingest.base import ALLOWED_EXTENSIONS, IngestError, check_file
from tokenops_cost_auditor.services.lifecycle import auditlog

router = APIRouter(prefix="/api/v1", tags=["audits"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHUNK = 1024 * 1024


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def current_user(request: Request, x_user_email: str | None = Header(default=None)) -> str:
    """Pre-D8 auth stub (magic-link sessions replace this at D8). Refused in prod."""
    settings: Settings = request.app.state.settings
    if settings.app_env == "prod" or not x_user_email or not EMAIL_RE.match(x_user_email):
        raise HTTPException(status_code=401, detail="authentication required")
    request.state.user_email = x_user_email.lower()  # NFR-12 rate-limit key
    return x_user_email.lower()


def payment_gate(user_email: str = Depends(current_user)) -> str:
    """Pre-D9 stub: FR-18 'paid before upload' enforcement lands at D9 here."""
    return user_email


@router.post("/audits", status_code=201)
@limiter.limit("10/minute")
def create_audit(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
    user_email: str = Depends(payment_gate),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
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

        audit = Audit(user_id=user.id, status="queued")
        session.add(audit)
        session.flush()
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
    return JSONResponse(status_code=201, content={"audit_id": audit_id, "replayed": False})


@router.get("/audits/{audit_id}/status")
def audit_status(
    request: Request, audit_id: str, user_email: str = Depends(current_user)
) -> dict[str, object]:
    with _session(request) as session:
        audit = session.get(Audit, audit_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="audit not found")
        owner = session.get(User, audit.user_id)
        if owner is None or owner.email != user_email:
            raise HTTPException(status_code=404, detail="audit not found")
        body: dict[str, object] = {"audit_id": audit.id, "status": audit.status}
        if audit.valid_pct is not None:
            body["valid_pct"] = audit.valid_pct
        if audit.error:
            body["error"] = audit.error
        if audit.status == "queued":
            body["queue_position"] = queue_position(session, audit)  # NFR-13
        return body
