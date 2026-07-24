"""Read API (S-6, R-SDK-PLATFORM) — the READ half of the platform.

GET /api/v1/audits                    (scope read:audits)
GET /api/v1/audits/{id}/findings      (scope read:findings)

Every response is COUNTS AND DOLLARS ONLY (FR-22): audit status, token counts,
spend figures, finding severities and dollar impact. No prompt or completion
text exists to return — the schema has no such column. Every query is scoped to
the principal's ACTIVE WORKSPACE (O-1, R-ORG — a read token returns the
token-owner's workspace data, visible to its members); an audit outside that
workspace is a 404, never a 403, so token holders can't probe which audit ids
exist.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from tokenops_cost_auditor.persistence.models import Audit, FindingRow
from tokenops_cost_auditor.persistence.repo import active_workspace_id
from tokenops_cost_auditor.web.api_auth import ReadPrincipal, require_read_scope

router = APIRouter(prefix="/api/v1", tags=["read-api"])

_MAX_PAGE = 200
_DEFAULT_PAGE = 50

# Module-level dependency singletons — one per required scope. Injected via
# Annotated (the modern FastAPI form) because a Depends() into a non-scalar
# type in a plain default trips ruff B008.
_needs_audits = require_read_scope("read:audits")
_needs_findings = require_read_scope("read:findings")


@router.get("/audits")
def list_audits(
    request: Request,
    principal: Annotated[ReadPrincipal, Depends(_needs_audits)],
    limit: int = Query(default=_DEFAULT_PAGE, ge=1, le=_MAX_PAGE),
) -> JSONResponse:
    """The caller's most recent audits — counts and dollars only."""
    with request.app.state.session_factory() as session:
        ws = active_workspace_id(session, principal.user_id)
        rows = (
            session.execute(
                select(Audit)
                .where(Audit.workspace_id == ws)
                .order_by(Audit.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        # One grouped count instead of N per-audit queries.
        ids = [a.id for a in rows]
        counts: dict[str, int] = {}
        if ids:
            counts = dict(
                session.execute(
                    select(FindingRow.audit_id, func.count(FindingRow.id))
                    .where(FindingRow.audit_id.in_(ids))
                    .group_by(FindingRow.audit_id)
                ).all()
            )
        audits = [
            {
                "id": a.id,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "records": a.row_count,
                "observed_days": a.observed_days,
                "total_spend_usd": a.total_spend_usd,
                "projected_spend_usd": a.projected_spend_usd,
                "savings_pct": a.savings_pct,
                "equiv_spend": a.equiv_spend,
                "findings": counts.get(a.id, 0),
            }
            for a in rows
        ]
    return JSONResponse(status_code=200, content={"audits": audits})


@router.get("/audits/{audit_id}/findings")
def list_findings(
    request: Request,
    audit_id: str,
    principal: Annotated[ReadPrincipal, Depends(_needs_findings)],
) -> JSONResponse:
    """The findings inside one of the caller's audits — ranked, counts/dollars
    plus the generated fix guidance. Never any customer prompt/completion text."""
    with request.app.state.session_factory() as session:
        audit = session.get(Audit, audit_id)
        # Tenant isolation: outside the principal's active workspace (or absent)
        # is an identical 404 — no existence oracle across workspaces (O-1).
        if audit is None or audit.workspace_id != active_workspace_id(session, principal.user_id):
            raise HTTPException(status_code=404, detail="audit not found")
        rows = (
            session.execute(
                select(FindingRow)
                .where(FindingRow.audit_id == audit_id)
                .order_by(FindingRow.monthly_impact_usd.desc())
            )
            .scalars()
            .all()
        )
        findings = [
            {
                "id": f.finding_id,
                "detector": f.detector,
                "route": f.route,
                "severity": f.severity,
                "confidence": f.confidence,
                "monthly_cost_impact_usd": f.monthly_impact_usd,
                "fix": f.fix_text,
            }
            for f in rows
        ]
    return JSONResponse(status_code=200, content={"audit_id": audit_id, "findings": findings})
