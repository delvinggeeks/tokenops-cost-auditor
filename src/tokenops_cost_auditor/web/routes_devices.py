"""WP-CC-LINK — device link + counts-only shipping for Claude Code fleets (T3).

THE LAW (R-CC-LINK 2, permanent): ONE HUMAN ACTION IS THE FLOOR, NEVER
ZERO. Enforcement is honestly split (cold-review f.2): the TTY prompt
lives in the reference CLI; the server can only verify that consent was
ASSERTED — a direct API caller asserting it has still performed a human
action with a code they had to obtain from their own dashboard. The
assertion, not a verified fact, is what the device row (NOT NULL) and the
audit log record — stated plainly here so nobody mistakes the boundary.

Token handling mirrors R-CONNECT keys: hashed at rest via the keyed
one-way fingerprint (plaintext exists only in the customer's own config
file), revocation is a dashboard click, revoked devices are refused with
a plain-words error. Ships enter the SAME T1 pipeline as uploads
(FR-26 idempotency honored), marked paid_via="collector".
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import Device, IdempotencyKey, LinkCode, User, utcnow
from tokenops_cost_auditor.persistence.repo import (
    active_role,
    find_idempotent_audit,
    get_or_create_user,
    workspace_id_for,
)
from tokenops_cost_auditor.persistence.repo import (
    create_audit as repo_create_audit,
)
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.ingest.base import IngestError, check_file
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.routes_sources import user_plan

router = APIRouter(tags=["collector"])

CODE_TTL_MIN = 10
CONSENT_TEXT = (
    "TokenOps collects TOKEN COUNTS ONLY from your Claude Code transcripts — "
    "models, timestamps, token totals per call. Never a prompt, never a "
    "completion, never file contents. Ships on your schedule (you run or cron "
    "`ship`). Revoke any time from Sources; revocation is immediate."
)


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


@router.post("/sources/claude-code/code", response_class=HTMLResponse)
def issue_link_code(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """Dashboard action: mint a short-lived one-shot link code, shown once.
    Plan-gated at LINK time (the collector is a subscriber deliverable);
    ships are then per-device, no further gate."""
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: linking a machine is a MANAGE_SOURCES action — owner/admin only.
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_SOURCES,
            detail="only an owner or admin can link a machine",
        )
        plan = user_plan(session, user.id)
        if plan not in ("pro", "team"):
            raise HTTPException(
                status_code=403,
                detail="the Claude Code collector is part of Pro — see /billing",
            )
        code = secrets.token_urlsafe(9)
        session.add(
            LinkCode(
                user_id=user.id,
                code_hash=credential_fingerprint(settings.secret_key, code),
                expires_at=datetime.now(UTC) + timedelta(minutes=CODE_TTL_MIN),
            )
        )
        auditlog.append(session, user_email, "device.code_issued", user.email)
        session.commit()
    tpl = request.app.state.jinja.get_template("app/_link_code.html")
    return HTMLResponse(
        tpl.render(code=code, ttl=CODE_TTL_MIN, base=str(request.base_url).rstrip("/"))
    )


@router.post("/api/v1/collector/link")
@limiter.limit("5/minute")
def link_device(request: Request, payload: dict[str, object]) -> JSONResponse:
    """Exchange a link code for a device token. Refuses without the consent
    ASSERTION (R-CC-LINK 2 — see the module docstring for the honest trust
    boundary: the prompt lives in the CLI; the server records the claim)."""
    settings = request.app.state.settings
    code = str(payload.get("code", "")).strip()
    hostname = str(payload.get("hostname", "")).strip()[:120] or "unknown-machine"
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    if payload.get("consent") is not True:
        raise HTTPException(
            status_code=400,
            detail="consent required — run `tokenops-cost-auditor link` and agree at the prompt",
        )
    now = datetime.now(UTC)
    with _session(request) as session:
        row = session.execute(
            select(LinkCode).where(
                LinkCode.code_hash == credential_fingerprint(settings.secret_key, code)
            )
        ).scalar_one_or_none()
        if row is None or row.consumed_at is not None:
            raise HTTPException(status_code=404, detail="unknown or already-used code")
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires < now:
            raise HTTPException(
                status_code=410, detail="code expired — issue a fresh one from Sources"
            )
        # Atomic one-shot claim (cold-review f.1 — the check-then-set race
        # class, third catch today): UPDATE-where-unconsumed, rowcount-checked.
        # Two concurrent exchanges of one code cannot both mint a device.
        claimed = session.execute(
            update(LinkCode)
            .where(LinkCode.id == row.id, LinkCode.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        if cast("CursorResult[Any]", claimed).rowcount != 1:
            raise HTTPException(status_code=404, detail="unknown or already-used code")
        token = secrets.token_urlsafe(32)
        device = Device(
            user_id=row.user_id,
            workspace_id=workspace_id_for(session, row.user_id),  # O-0
            hostname=hostname,
            token_hash=credential_fingerprint(settings.secret_key, token),
            consent_at=now,
        )
        session.add(device)
        user = session.get(User, row.user_id)
        auditlog.append(
            session,
            user.email if user else row.user_id,
            "device.linked",
            hostname,
            {"consent": CONSENT_TEXT[:80] + "…"},
        )
        session.commit()
        device_id = device.id
    return JSONResponse(
        status_code=201,
        content={"device_token": token, "device_id": device_id, "consent_recorded": True},
    )


def _device(request: Request, session: Session, token: str | None) -> Device:
    if not token:
        raise HTTPException(status_code=401, detail="device token required")
    settings = request.app.state.settings
    device = session.execute(
        select(Device).where(
            Device.token_hash.is_not(None),
            Device.token_hash == credential_fingerprint(settings.secret_key, token),
        )
    ).scalar_one_or_none()
    if device is None or device.revoked_at is not None:
        raise HTTPException(
            status_code=401, detail="device not linked or revoked — link again from Sources"
        )
    return device


@router.post("/api/v1/collector/ship", status_code=201)
@limiter.limit("10/minute")
def ship(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Counts-only JSONL from the collector enters the same T1 pipeline as
    an upload. FR-26 idempotency makes scheduled re-ships safe."""
    settings = request.app.state.settings
    with _session(request) as session:
        device = _device(request, session, x_device_token)
        plan = user_plan(session, device.user_id)
        if plan not in ("pro", "team"):
            raise HTTPException(
                status_code=402, detail="subscription lapsed — ships pause until it resumes"
            )
        if idempotency_key:
            existing = find_idempotent_audit(session, device.user_id, idempotency_key)
            if existing is not None:
                session.commit()
                return JSONResponse(
                    status_code=200, content={"audit_id": existing.id, "replayed": True}
                )
        audit = repo_create_audit(session, device.user_id)
        audit.paid_via = "collector"
        audit.source_id = device.id  # R-MULTI-SOURCE attribution, device-grade
        upload_dir = Path(settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / "original.jsonl"
        max_bytes = settings.max_upload_mb * 1024 * 1024
        written = 0
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="ship exceeds the upload limit")
                out.write(chunk)
        try:
            check_file(dest, settings.max_upload_mb)
        except IngestError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audit.upload_path = str(dest)
        if idempotency_key:
            session.add(
                IdempotencyKey(user_id=device.user_id, key=idempotency_key, audit_id=audit.id)
            )
        device.last_ship_at = utcnow()
        auditlog.append(session, f"device:{device.hostname}", "device.shipped", audit.id)
        session.commit()
        audit_id = audit.id
    background.add_task(request.app.state.runner.run, audit_id)
    return JSONResponse(status_code=201, content={"audit_id": audit_id, "replayed": False})


@router.post("/sources/devices/{device_id}/revoke", response_model=None)
def revoke_device(
    request: Request, device_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: revoke is a MANAGE_SOURCES mutation — owner/admin only. The device
        # LIST display stays workspace-scoped (sources_page, explorer); mutating 403s.
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_SOURCES,
            detail="only an owner or admin can unlink a machine",
        )
        device = session.get(Device, device_id)
        if device is None or device.user_id != user.id:
            raise HTTPException(status_code=404, detail="device not found")
        device.revoked_at = utcnow()
        # Parity with source revokes (authority law §5c): the credential
        # material is DELETED, not just flagged — the row keeps its identity
        # for audit attribution, the key is gone.
        device.token_hash = None
        auditlog.append(session, user_email, "device.revoked", device.hostname)
        session.commit()
    return RedirectResponse("/sources", status_code=303)
