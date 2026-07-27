"""GitHub Copilot seat-governance upload (WP-COPILOT-AGG, R-COPILOT).

Upload-first (no GitHub API dependency): a customer downloads their Copilot
seats export (the /orgs/{org}/copilot/billing/seats JSON, or a CSV) and
uploads it here. We read seat DATES only (never a login, never content —
FR-22), find idle seats, and land the same report as a token audit, with
the seat finding labeled seat governance. Observe-only (X-02): we surface
idle seats; reclaiming is the customer's action in GitHub.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.repo import active_role, get_or_create_user
from tokenops_cost_auditor.services.copilot.report import run_seat_audit
from tokenops_cost_auditor.services.copilot.seats import DEFAULT_IDLE_DAYS, DEFAULT_SEAT_RATE_USD
from tokenops_cost_auditor.services.report.signer import sign_report_url
from tokenops_cost_auditor.web import authz

log = structlog.get_logger("tokenops_cost_auditor.copilot")

router = APIRouter(tags=["copilot"])

MAX_SEAT_UPLOAD_MB = 10  # a seats export is small; a big file is a wrong upload


@router.post("/copilot/seats", response_model=None)
@limiter.limit("10/minute")
def upload_seats(
    request: Request,
    file: UploadFile,
    idle_days: int = Form(DEFAULT_IDLE_DAYS),
    rate_usd: float = Form(DEFAULT_SEAT_RATE_USD),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    settings = request.app.state.settings
    raw = file.file.read(MAX_SEAT_UPLOAD_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_SEAT_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="that file is far larger than a seat export")
    # bound the customer-facing knobs (a negative rate or absurd window is a typo)
    idle_days = max(1, min(idle_days, 365))
    rate_usd = max(0.0, min(rate_usd, 1000.0))
    try:
        blob = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="the seat export must be UTF-8 JSON or CSV"
        ) from None

    with request.app.state.session_factory() as session:
        user = get_or_create_user(session, user_email)
        # O-2 RBAC: a seat audit IS an audit run — gate it exactly like the twin
        # POST /api/v1/audits (routes_upload.create_audit). Without this a viewer
        # bypassed the run-audits gate on this route (the connect-wizard bug class).
        authz.ensure(
            active_role(session, user.id),
            authz.Perm.RUN_AUDITS,
            detail="a viewer can view reports but can't run audits",
        )
        session.commit()
        try:
            audit_id = run_seat_audit(
                session, settings, user.id, blob, idle_days=idle_days, rate_usd=rate_usd
            )
        except ValueError as exc:  # malformed export — user-safe message
            raise HTTPException(status_code=400, detail=str(exc)) from None
    token = sign_report_url(settings.secret_key, audit_id)
    log.info("copilot.seat_audit", audit_id=audit_id)
    return RedirectResponse(url=f"/r/{token}", status_code=303)
