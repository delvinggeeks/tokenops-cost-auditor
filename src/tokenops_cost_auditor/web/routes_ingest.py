"""S-0 (R-SDK-PLATFORM): the ingest DSN — one env var in the client's stack.

The adoption wedge of PLAN-SDK: a customer mints an INGEST-ONLY key on
Sources, puts `TOKENOPS_COST_AUDITOR_DSN=https://ik_<key>@<host>` in their
environment, and their code (curl today; the S-1 SDK next) POSTs per-call
usage records to /api/v1/ingest. Records enter the same T1 pipeline as an
upload — full six-detector coverage, FR-26 idempotent.

Trust boundary, honestly: the key is WRITE-ONLY by construction — every
route it authorizes ingests counts; none reads. A leaked DSN can pollute
an account's usage data (visible in the runs ledger, revocable in one
click) but can never read a byte.

FR-22 AT THE DOOR: records are validated against a strict ALLOWLIST of
the documented generic-contract fields with bounded scalar values. An
unknown key (prompt, messages, content, anything) or an oversized string
is rejected loudly with a 422 naming the offender — we refuse the data we
promise never to hold, rather than silently dropping it (silent dropping
would teach integrators that sending text is fine).

Key hygiene mirrors the collector: hashed at rest (credential_fingerprint
context), shown once at mint, revoke DELETES the hash (authority law).
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import IdempotencyKey, IngestKey, utcnow
from tokenops_cost_auditor.persistence.repo import create_audit as repo_create_audit
from tokenops_cost_auditor.persistence.repo import find_idempotent_audit, get_or_create_user
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web.routes_sources import user_plan

log = structlog.get_logger("tokenops_cost_auditor.ingest")

router = APIRouter(tags=["ingest"])

MAX_RECORDS_PER_BATCH = 5_000  # stated in the 422, never silent
MAX_KEYS_PER_USER = 10

# The documented generic contract, as a strict allowlist. Field -> (kind,
# max_len for strings). Anything else is refused BY NAME.
_REQUIRED = ("ts", "provider", "model", "prompt_tokens", "completion_tokens")
_FIELDS: dict[str, tuple[str, int]] = {
    "ts": ("str", 40),
    "provider": ("str", 40),
    "model": ("str", 120),
    "prompt_tokens": ("int", 0),
    "completion_tokens": ("int", 0),
    "cached_tokens": ("int", 0),
    "cache_write_tokens": ("int", 0),
    "latency_ms": ("num", 0),
    "declared_max_tokens": ("int", 0),
    "endpoint": ("str", 120),
    "request_id": ("str", 120),
    "tag": ("str", 120),
    "prefix_hash": ("str", 64),
}
_CSV_COLUMNS = tuple(_FIELDS)


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _validate_record(idx: int, record: object) -> dict[str, Any]:
    """FR-22 door: strict allowlist, bounded scalars, loud refusals."""
    if not isinstance(record, dict):
        raise HTTPException(status_code=422, detail=f"records[{idx}] is not an object")
    unknown = sorted(set(record) - set(_FIELDS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"records[{idx}] carries fields outside the counts-only contract: "
                f"{', '.join(unknown)}. We never accept prompt or completion "
                f"content (FR-22) — send token counts; precompute prefix_hash "
                f"client-side if you want cache detection."
            ),
        )
    missing = [f for f in _REQUIRED if f not in record]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"records[{idx}] is missing required fields: {', '.join(missing)}",
        )
    out: dict[str, Any] = {}
    for name, value in record.items():
        kind, max_len = _FIELDS[name]
        if kind == "str":
            if not isinstance(value, str) or len(value) > max_len:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"records[{idx}].{name} must be a string of at most {max_len} characters"
                    ),
                )
        elif kind == "int":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"records[{idx}].{name} must be a non-negative integer",
                )
        elif isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            raise HTTPException(
                status_code=422,
                detail=f"records[{idx}].{name} must be a non-negative number",
            )
        out[name] = value
    return out


def _key_from_bearer(request: Request, session: Session, authorization: str | None) -> IngestKey:
    if not authorization or not authorization.startswith("Bearer ik_"):
        raise HTTPException(
            status_code=401,
            detail="send the ingest key: Authorization: Bearer ik_… (mint one on Sources)",
        )
    settings = request.app.state.settings
    token = authorization.removeprefix("Bearer ").strip()
    row = session.execute(
        select(IngestKey).where(
            IngestKey.key_hash == credential_fingerprint(settings.secret_key, token),
            IngestKey.key_hash.is_not(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="unknown or revoked ingest key")
    return row


@router.post("/api/v1/ingest")
@limiter.limit("60/minute")
def ingest(
    request: Request,
    background: BackgroundTasks,
    payload: dict[str, object],
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """A batch of per-call usage records -> the T1 pipeline (full coverage)."""
    settings = request.app.state.settings
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=422, detail='body must be {"records": [ … ]}')
    if len(records) > MAX_RECORDS_PER_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"batch exceeds {MAX_RECORDS_PER_BATCH} records — split it",
        )
    clean = [_validate_record(i, r) for i, r in enumerate(records)]

    with _session(request) as session:
        key = _key_from_bearer(request, session, authorization)
        plan = user_plan(session, key.user_id)
        if plan not in ("pro", "team"):
            raise HTTPException(
                status_code=402,
                detail="subscription lapsed — ingest pauses until it resumes",
            )
        if idempotency_key:
            existing = find_idempotent_audit(session, key.user_id, idempotency_key)
            if existing is not None:
                session.commit()
                return JSONResponse(
                    status_code=200, content={"audit_id": existing.id, "replayed": True}
                )
        audit = repo_create_audit(session, key.user_id)
        audit.paid_via = "sdk"
        audit.source_id = key.id  # R-MULTI-SOURCE attribution, key-grade
        upload_dir = Path(settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / "original.csv"
        # The documented generic-CSV contract IS the wire format — records
        # land as the CSV the T1 pipeline already parses; zero new ingest code.
        with dest.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
            writer.writeheader()
            for row in clean:
                writer.writerow(row)
        audit.upload_path = str(dest)
        if idempotency_key:
            session.add(IdempotencyKey(user_id=key.user_id, key=idempotency_key, audit_id=audit.id))
        key.last_used_at = utcnow()
        auditlog.append(session, f"ingest-key:{key.label}", "ingest.received", audit.id)
        session.commit()
        audit_id = audit.id
    background.add_task(request.app.state.runner.run, audit_id)
    return JSONResponse(
        status_code=201,
        content={"audit_id": audit_id, "records": len(clean), "replayed": False},
    )


@router.post("/sources/sdk/key", response_class=HTMLResponse)
@limiter.limit("5/minute")
def mint_key(
    request: Request,
    label: str = Form("api service"),
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """Mint an ingest key — shown once, stored hashed. Pro+ (an SDK stream
    is a subscriber deliverable, same law as the collector)."""
    import secrets

    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        plan = user_plan(session, user.id)
        if plan not in ("pro", "team"):
            raise HTTPException(
                status_code=403,
                detail="SDK ingest keys are part of Pro — see /billing",
            )
        active = session.execute(
            select(IngestKey).where(IngestKey.user_id == user.id, IngestKey.key_hash.is_not(None))
        ).scalars()
        if len(list(active)) >= MAX_KEYS_PER_USER:
            raise HTTPException(
                status_code=403,
                detail=f"{MAX_KEYS_PER_USER} active keys is the limit — revoke one first",
            )
        token = f"ik_{secrets.token_urlsafe(32)}"
        row = IngestKey(
            user_id=user.id,
            label=label.strip()[:80] or "api service",
            key_hash=credential_fingerprint(settings.secret_key, token),
        )
        session.add(row)
        auditlog.append(session, user_email, "ingest.key_minted", row.label)
        session.commit()
    host = settings.app_base_url or str(request.base_url).rstrip("/")
    tpl = request.app.state.jinja.get_template("app/_ingest_key.html")
    return HTMLResponse(tpl.render(token=token, host=host))


@router.post("/sources/sdk/{key_id}/revoke")
def revoke_key(
    request: Request, key_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    """Revoke = the hash is DELETED (authority law) — ingest stops now."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        row = session.get(IngestKey, key_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="key not found")
        row.key_hash = None
        row.revoked_at = datetime.now(UTC)
        auditlog.append(session, user_email, "ingest.key_revoked", row.label)
        session.commit()
    return RedirectResponse(url="/sources", status_code=303)
