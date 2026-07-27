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
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import IdempotencyKey, IngestKey, User, utcnow
from tokenops_cost_auditor.persistence.repo import (
    active_role,
    find_idempotent_audit,
    get_or_create_user,
    workspace_id_for,
)
from tokenops_cost_auditor.persistence.repo import create_audit as repo_create_audit
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.routes_sources import user_plan

log = structlog.get_logger("tokenops_cost_auditor.ingest")

router = APIRouter(tags=["ingest"])

MAX_RECORDS_PER_BATCH = 5_000  # stated in the 422, never silent
MAX_KEYS_PER_USER = 10
# per-field ceiling (cold-review f.2): a day's tokens/latency for one call
# cannot plausibly exceed this; anything larger is malformed, not real.
_MAX_COUNT = 1_000_000_000_000


def _ingest_rate_key(request: Request) -> str:
    """Per-key FAIRNESS bucket (cold-review f.5): the bearer-auth route never
    populates request.state.user_email, so the global user-or-ip key would
    bucket every customer's traffic — and every bad-token 401 — under one
    shared IP. Key on a HASH of the bearer token (never the plaintext) so one
    noisy key can't starve another; unauthenticated calls fall to IP.

    This bucket ALONE does not bound abuse: an attacker varying token bytes
    would mint a fresh bucket per guess (re-gate finding). The stacked
    per-IP ceiling (_INGEST_IP_LIMIT) is the real bound — it caps total
    ingest attempts from one source regardless of how many token variations
    it tries. Fairness and abuse-bounding are two limits, deliberately."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ik_"):
        digest = hashlib.sha256(auth.encode()).hexdigest()[:32]
        return f"ingest:{digest}"
    return f"ip:{get_remote_address(request)}"


# The brute-force / DoS ceiling: total ingest from one IP, whatever tokens it
# presents. Set well above a single busy customer's per-key budget so it
# only bites genuine abuse (the token itself is 256-bit; entropy, not rate,
# defeats guessing — this bounds resource use).
_INGEST_IP_LIMIT = "300/minute"


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


def _bump_usage(key: IngestKey) -> None:
    """R-PLATFORM slice 5: request count + last-used, counts only (FR-22).

    Best-effort BY DESIGN — called from inside a try/except, because
    metering must never turn a successful ingest into a failed one."""
    key.last_used_at = utcnow()
    key.request_count += 1


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
    # cold-review f.1: presence is not enough — a required field that is
    # empty ("") passes the door then fails EVERY row downstream, so the
    # batch 201s while the pipeline silently rejects it. Reject empties here.
    missing = [f for f in _REQUIRED if not str(record.get(f, "")).strip()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"records[{idx}] is missing or empty required fields: {', '.join(missing)}",
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
            # cold-review f.2: a ceiling too — an absurd token count would
            # distort cost totals and detector thresholds downstream.
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= _MAX_COUNT
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"records[{idx}].{name} must be an integer in [0, {_MAX_COUNT:,}]",
                )
        elif (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not 0 <= value <= _MAX_COUNT
        ):
            raise HTTPException(
                status_code=422,
                detail=f"records[{idx}].{name} must be a number in [0, {_MAX_COUNT:,}]",
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
@limiter.limit(_INGEST_IP_LIMIT, key_func=get_remote_address)  # abuse ceiling per source IP
@limiter.limit("60/minute", key_func=_ingest_rate_key)  # fair per-key budget
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
        try:
            _bump_usage(key)
        except Exception:  # best-effort (issue #59): metering never fails the call
            log.warning("ingest_key.usage_bump_failed", key_id=key.id, exc_info=True)
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
        # O-2 RBAC: minting an ingest key is a MANAGE_SOURCES action — owner/admin only.
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_SOURCES,
            detail="only an owner or admin can mint ingest keys",
        )
        # Lock the user row so concurrent mints serialize on the count
        # (cold-review f.3 — the saved-views/link-code race class, caught
        # again). Row lock on Postgres; no-op on SQLite.
        session.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        plan = user_plan(session, user.id)
        if plan not in ("pro", "team"):
            raise HTTPException(
                status_code=403,
                detail="SDK ingest keys are part of Pro — see /billing",
            )
        # O-1: minting is an owner-only MUTATE with a per-user cap — stays
        # user-scoped (the ingest-key LIST display flips to workspace in
        # sources_page; revoke below is likewise owner-scoped until O-2 RBAC).
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
            workspace_id=workspace_id_for(session, user.id),  # O-0
            label=label.strip()[:80] or "api service",
            key_hash=credential_fingerprint(settings.secret_key, token),
        )
        session.add(row)
        auditlog.append(session, user_email, "ingest.key_minted", row.label)
        session.commit()
    host = (settings.app_base_url or str(request.base_url)).rstrip("/")
    # cold-review f.4: the DSN embeds the token as https://<token>@<host>.
    # If a misconfigured host carries no scheme, prepend one HERE rather
    # than let the template's .replace() silently drop the token — a DSN
    # without its credential is unrecoverable, shown-once.
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    tpl = request.app.state.jinja.get_template("app/_ingest_key.html")
    return HTMLResponse(tpl.render(token=token, host=host))


@router.post("/sources/sdk/{key_id}/revoke")
def revoke_key(
    request: Request, key_id: str, user_email: str = Depends(current_user)
) -> RedirectResponse:
    """Revoke = the hash is DELETED (authority law) — ingest stops now."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: revoking a key is a MANAGE_SOURCES action — owner/admin only.
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.MANAGE_SOURCES,
            detail="only an owner or admin can revoke ingest keys",
        )
        row = session.get(IngestKey, key_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="key not found")
        row.key_hash = None
        row.revoked_at = datetime.now(UTC)
        auditlog.append(session, user_email, "ingest.key_revoked", row.label)
        session.commit()
    return RedirectResponse(url="/sources", status_code=303)
