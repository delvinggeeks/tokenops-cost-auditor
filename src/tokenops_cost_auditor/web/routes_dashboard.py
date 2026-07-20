"""Owner dashboard, findings, guide and tour (PLAN-V15 WP-2 + V-D4g).

SSR + htmx partials only — no SPA (X-05 as relaxed 2026-07-20). Every
widget renders standalone at /dashboard/w/<key> so htmx can refresh one
widget without redrawing the page.

Copy discipline: headline strings come from the help registry's `plain`
phrasing; detector identifiers appear only inside the expanded drawer
(R-PERSONA jargon law). Depth (c) renders why → evidence → fix → verify →
methodology, in that fixed order (R-CLARITY §1).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
    User,
    utcnow,
)
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.dashboard import metrics
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web import help as help_registry
from tokenops_cost_auditor.web.routes_sources import user_plan

router = APIRouter(tags=["dashboard"])

VERDICTS = ("applied", "dismissed", "not_relevant")
WIDGETS = ("savings", "spend_trend", "waste_trend", "top_findings", "sources", "next_audit")


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _render(request: Request, template: str, **ctx: object) -> HTMLResponse:
    tpl = request.app.state.jinja.get_template(template)
    return HTMLResponse(tpl.render(help=help_registry, **ctx))


def _shell_ctx(session: Session, request: Request, user: User, page: str) -> dict[str, object]:
    latest = metrics.latest_audit(session, user.id)
    freshness = (
        f"Data as of {(latest.report_ready_at or latest.created_at):%Y-%m-%d %H:%M} UTC"
        if latest
        else "No data yet — connect a source or upload a log file"
    )
    return {
        "page": page,
        "plan": user_plan(session, user.id),
        "freshness": freshness,
        "user_email": user.email,
        "purpose": help_registry.purpose(page),
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        w_savings, _ = metrics.savings(session, user.id)
        ctx = _shell_ctx(session, request, user, "overview")
        return _render(
            request,
            "app/dashboard.html",
            widgets={
                "savings": w_savings,
                "spend_trend": metrics.spend_trend(session, user.id),
                "waste_trend": metrics.waste_trend(session, user.id),
                "top_findings": metrics.top_findings(session, user.id),
                "sources": metrics.sources_health(session, user.id),
                "next_audit": metrics.next_audit(session, user.id),
            },
            show_tour=user.tour_dismissed_at is None,
            **ctx,
        )


@router.get("/dashboard/w/{key}", response_class=HTMLResponse)
def widget_partial(
    request: Request, key: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """One widget, standalone — the htmx refresh target."""
    if key not in WIDGETS:
        raise HTTPException(status_code=404, detail="unknown widget")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        if key == "savings":
            widget, _ = metrics.savings(session, user.id)
        else:
            widget = getattr(metrics, {"sources": "sources_health"}.get(key, key))(session, user.id)
        return _render(request, f"app/widgets/_{key}.html", w=widget, standalone=True)


@router.get("/findings", response_class=HTMLResponse)
def findings_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        audit = metrics.latest_audit(session, user.id)
        rows = (
            session.execute(
                select(FindingRow)
                .where(FindingRow.audit_id == audit.id)
                .order_by(FindingRow.monthly_impact_usd.desc())
            )
            .scalars()
            .all()
            if audit
            else []
        )
        verdicts = {
            fb.finding_id: fb.verdict
            for fb in (
                session.execute(select(FindingFeedback).where(FindingFeedback.audit_id == audit.id))
                .scalars()
                .all()
                if audit
                else []
            )
        }
        settings = request.app.state.settings
        items = [
            {
                "finding_id": r.finding_id,
                "detector": r.detector,
                # headline depth: plain phrasing only (R-PERSONA jargon law)
                "plain": help_registry.detector(r.detector, settings).plain,
                "severity": r.severity,
                "confidence": r.confidence,
                "monthly_usd": round(float(r.monthly_impact_usd), 2),
                "verdict": verdicts.get(r.finding_id),
            }
            for r in rows
        ]
        ctx = _shell_ctx(session, request, user, "findings")
        return _render(
            request,
            "app/findings.html",
            items=items,
            audit=audit,
            show_tour=False,
            **ctx,
        )


@router.get("/findings/{audit_id}/{finding_id}", response_class=HTMLResponse)
def finding_drawer(
    request: Request, audit_id: str, finding_id: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """Depth (c): why → evidence → fix → verify → methodology (R-CLARITY §1).
    Rendered into a right-hand drawer by htmx (familiarity principle)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        audit = session.get(Audit, audit_id)
        if audit is None or audit.user_id != user.id:
            raise HTTPException(status_code=404, detail="audit not found")
        row = session.execute(
            select(FindingRow).where(
                FindingRow.audit_id == audit_id, FindingRow.finding_id == finding_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="finding not found")
        fb = session.execute(
            select(FindingFeedback).where(
                FindingFeedback.audit_id == audit_id,
                FindingFeedback.finding_id == finding_id,
            )
        ).scalar_one_or_none()
        detector_help = help_registry.detector(row.detector, request.app.state.settings)
        return _render(
            request,
            "app/_finding_drawer.html",
            row=row,
            audit=audit,
            h=detector_help,
            verdict=fb.verdict if fb else None,
        )


@router.post("/findings/{audit_id}/{finding_id}/feedback", response_model=None)
def capture_feedback(
    request: Request,
    audit_id: str,
    finding_id: str,
    verdict: str = Form(...),
    savings_realized_usd: float | None = Form(default=None),
    user_email: str = Depends(current_user),
) -> HTMLResponse:
    """L0 capture (docs/12 Stage 3). Idempotent: re-voting updates in place."""
    if verdict not in VERDICTS:
        raise HTTPException(status_code=400, detail="unknown verdict")
    if savings_realized_usd is not None and savings_realized_usd < 0:
        raise HTTPException(status_code=400, detail="savings must be >= 0")
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        audit = session.get(Audit, audit_id)
        if audit is None or audit.user_id != user.id:
            raise HTTPException(status_code=404, detail="audit not found")
        existing = session.execute(
            select(FindingFeedback).where(
                FindingFeedback.audit_id == audit_id,
                FindingFeedback.finding_id == finding_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                FindingFeedback(
                    audit_id=audit_id,
                    finding_id=finding_id,
                    verdict=verdict,
                    savings_realized_usd=savings_realized_usd,
                    actor=user.email,
                )
            )
        else:
            existing.verdict = verdict
            if savings_realized_usd is not None:
                existing.savings_realized_usd = savings_realized_usd
            existing.ts = utcnow()
        auditlog.append(session, user.email, "finding.feedback", finding_id, {"verdict": verdict})
        session.commit()
        widget, _ = metrics.savings(session, user.id)
        # htmx swaps the savings widget back in — the applied fix visibly
        # flows into the headline (R-DESIGN-ADDENDUM 2a).
        return _render(request, "app/widgets/_savings.html", w=widget, standalone=True)


@router.post("/tour/dismiss", response_model=None)
def dismiss_tour(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        user.tour_dismissed_at = utcnow()
        session.commit()
    return HTMLResponse("")  # htmx removes the tour node


@router.post("/tour/replay", response_model=None)
def replay_tour(request: Request, user_email: str = Depends(current_user)) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        user.tour_dismissed_at = None
        session.commit()
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/guide", response_class=HTMLResponse)
def guide_index(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ctx = _shell_ctx(session, request, user, "guide")
        return _render(
            request,
            "app/guide.html",
            pages=help_registry.guide_index(),
            page_body=None,
            show_tour=False,
            **ctx,
        )


@router.get("/guide/{slug}", response_class=HTMLResponse)
def guide_detail(
    request: Request, slug: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        try:
            body = help_registry.guide_page(slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="guide page not found") from exc
        ctx = _shell_ctx(session, request, user, "guide")
        return _render(
            request,
            "app/guide.html",
            pages=help_registry.guide_index(),
            page_body=body,
            show_tour=False,
            **ctx,
        )
