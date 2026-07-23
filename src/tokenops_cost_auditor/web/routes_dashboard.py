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

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
from tokenops_cost_auditor.services.alerts import dispatch as alerts_dispatch
from tokenops_cost_auditor.services.dashboard import metrics
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans
from tokenops_cost_auditor.web import help as help_registry
from tokenops_cost_auditor.web.routes_sources import user_plan

router = APIRouter(tags=["dashboard"])

VERDICTS = ("applied", "dismissed", "not_relevant")
# Server-side sort keys for the findings table. SSR links, not JS —
# a header that looks sortable IS sortable (familiarity principle).
SORTS = {
    "impact": lambda i: -i["monthly_usd"],
    "title": lambda i: i["plain"].lower(),
    "severity": lambda i: {"high": 0, "med": 1, "low": 2}.get(i["severity"], 3),
    "confidence": lambda i: i["confidence"],
}
WIDGETS = (
    "savings",
    "yesterday",
    "forecast",
    "spend_trend",
    "waste_trend",
    "top_findings",
    "sources",
    "next_audit",
    "alerts",
    "pipeline",  # W0 spine — live states + self-poll while a run is in flight
)


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _render(request: Request, template: str, **ctx: object) -> HTMLResponse:
    tpl = request.app.state.jinja.get_template(template)
    return HTMLResponse(tpl.render(help=help_registry, **ctx))


def _shell_ctx(
    session: Session, request: Request, user: User, page: str, count_activity: bool = True
) -> dict[str, object]:
    latest = metrics.latest_audit(session, user.id)
    freshness = (
        f"Data as of {(latest.report_ready_at or latest.created_at):%Y-%m-%d %H:%M} UTC"
        if latest
        else "No data yet — connect a source or upload a log file"
    )
    plan_key = user_plan(session, user.id)
    from tokenops_cost_auditor.services.dashboard import activity

    return {
        "page": page,
        "plan": plan_key,
        # Display name from THE catalogue — `plan|title` on the internal key
        # would resurrect "Team" after the R-SAAS-BASICS rename.
        "plan_name": plans.get(request.app.state.settings, plan_key).name,
        "freshness": freshness,
        "user_email": user.email,
        "purpose": help_registry.purpose(page),
        # Wave B: the topbar bell's "what's new since you last looked" count.
        # Skipped on /activity, which resets and renders 0 itself (no double work).
        "unseen_activity": activity.unseen_count(session, user) if count_activity else 0,
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        w_savings, _ = metrics.savings(session, user.id)
        ctx = _shell_ctx(session, request, user, "overview")
        watching = alerts_dispatch.plan_watches(request.app.state.settings, str(ctx["plan"]))
        return _render(
            request,
            "app/dashboard.html",
            widgets={
                "savings": w_savings,
                "yesterday": metrics.yesterday_spend(
                    session, request.app.state.pricing_table, user.id
                ),
                "forecast": metrics.forecast(session, request.app.state.pricing_table, user.id),
                "spend_trend": metrics.spend_trend(session, user.id),
                "waste_trend": metrics.waste_trend(session, user.id),
                "top_findings": metrics.top_findings(session, user.id),
                "sources": metrics.sources_health(session, user.id),
                "next_audit": metrics.next_audit(session, user.id),
                "alerts": metrics.alerts_armed(session, user.id, watching=watching),
                "pipeline": metrics.pipeline(
                    session, request.app.state.pricing_table, user.id, watching=watching
                ),
            },
            # Wave A activation checklist: shown until every step is done or the
            # customer hides it (a cookie — a non-critical preference, no schema).
            onboarding=(
                None
                if request.cookies.get("onboarding_hidden")
                else metrics.onboarding(session, user.id)
            ),
            # why the loop looks the way it does — surfaces the unpriced-model
            # case so the ribbon's "waiting" is never a silent dead end.
            clarity=metrics.audit_clarity(session, request.app.state.pricing_table, user.id),
            support_email=request.app.state.settings.support_email,
            show_tour=user.tour_dismissed_at is None,
            **ctx,
        )


@router.post("/dashboard/onboarding/hide")
def hide_onboarding(request: Request, user_email: str = Depends(current_user)) -> RedirectResponse:
    """Let a customer dismiss the getting-started checklist. Cookie-scoped: it
    auto-hides on completion anyway, so this is only for 'I'd rather not see it'."""
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("onboarding_hidden", "1", max_age=365 * 86400, httponly=True, samesite="lax")
    return resp


@router.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """Wave B — the activity feed. Opening it marks everything seen, so the
    topbar bell resets: the customer's 'what's new' is always accurate."""
    from tokenops_cost_auditor.services.dashboard import activity

    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        events = activity.recent(session, user.id)
        ctx = _shell_ctx(session, request, user, "activity", count_activity=False)
        user.activity_seen_at = datetime.now(UTC)
        session.commit()
        return _render(request, "app/activity.html", events=events, show_tour=False, **ctx)


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
        widget: object
        if key == "savings":
            widget, _ = metrics.savings(session, user.id)
        elif key == "yesterday":
            widget = metrics.yesterday_spend(session, request.app.state.pricing_table, user.id)
        elif key == "forecast":
            widget = metrics.forecast(session, request.app.state.pricing_table, user.id)
        elif key == "alerts":
            watching = alerts_dispatch.plan_watches(
                request.app.state.settings, user_plan(session, user.id)
            )
            widget = metrics.alerts_armed(session, user.id, watching=watching)
        elif key == "pipeline":
            watching = alerts_dispatch.plan_watches(
                request.app.state.settings, user_plan(session, user.id)
            )
            live = metrics.pipeline(
                session, request.app.state.pricing_table, user.id, watching=watching
            )
            resp = _render(request, "app/widgets/_pipeline.html", w=live, standalone=True)
            if request.query_params.get("live") and not live["in_flight"]:
                # The polled render that catches the landing (R-LIVE-DASH):
                # announce it so every other widget refreshes once with the
                # run's numbers — no stale figures, no idle polling.
                resp.headers["HX-Trigger"] = "audit-landed"
            return resp
        else:
            fn = {"sources": "sources_health"}.get(key, key)
            widget = getattr(metrics, fn)(session, user.id)
        return _render(request, f"app/widgets/_{key}.html", w=widget, standalone=True)


def _owned_audit(session: Session, user: User, audit_id: str) -> Audit:
    audit = session.get(Audit, audit_id)
    if audit is None or audit.user_id != user.id:
        raise HTTPException(status_code=404, detail="audit not found")
    return audit


def _rejected_rows(audit: Audit) -> int:
    """Rows the validator rejected — read from the row_errors.csv the pipeline
    already writes (R-PIPELINE-UI-SEQ carve-out ii). 0 when clean or purged;
    the honest zero is a statement, not an absence."""
    if not audit.upload_path:
        return 0
    path = Path(audit.upload_path).parent / "row_errors.csv"
    if not path.exists():
        return 0
    return max(sum(1 for _ in path.open(encoding="utf-8")) - 1, 0)  # minus header


def _theater_stages(audit: Audit) -> list[dict[str, object]]:
    """The live pipeline, lit ONLY by data that has actually landed
    (R-PIPELINE-UI-SEQ carve-out i). Two checkpoints are observable today —
    ingest (row_count commits mid-run) and completion; price/detect/report
    land in one final commit, so mid-run they show as pending, never as done.
    Per-stage timings arrive with stage_events (WP-PIPELINE-UI)."""
    ingested = audit.row_count is not None
    done = audit.status == "done"
    running = audit.status == "processing"
    return [
        {
            "label": "Ingest",
            "state": "active" if (ingested or done) else ("live" if running else "waiting"),
            "value": f"{audit.row_count:,} rows" if ingested else "Reading your file",
            "note": f"{audit.valid_pct:.1f}% parsed" if audit.valid_pct is not None else "",
        },
        {
            "label": "Price",
            "state": "active" if done else ("live" if running and ingested else "waiting"),
            "value": f"${float(audit.total_spend_usd):,.2f} observed"
            if done and audit.total_spend_usd is not None
            else ("In progress" if running and ingested else "Waiting"),
            "note": "pinned pricing table" if done else "",
        },
        {
            "label": "Detect",
            "state": "active" if done else "waiting",
            "value": "Six deterministic detectors" if not done else "Findings ranked",
            "note": "lands with the final commit" if running else "",
        },
        {
            "label": "Report",
            "state": "active" if done else "waiting",
            "value": "Ready" if done else "Waiting",
            "note": f"{audit.observed_days or 0} day(s) observed" if done else "",
        },
    ]


@router.get("/audits/{audit_id}/progress", response_class=HTMLResponse)
def audit_progress(
    request: Request, audit_id: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """The live pipeline theater — where the browser lands after an upload."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        audit = _owned_audit(session, user, audit_id)
        # not via _shell_ctx: "upload"-adjacent pages have no help-registry
        # destination (its KeyError guard is deliberate), so the shell fields
        # are assembled directly — caught by rendering, not by review.
        plan_key = user_plan(session, user.id)
        return _render(
            request,
            "app/audit_progress.html",
            audit=audit,
            stages=_theater_stages(audit),
            rejected=_rejected_rows(audit),
            page="upload",
            plan=plan_key,
            plan_name=plans.get(request.app.state.settings, plan_key).name,
            freshness="",
            user_email=user.email,
            purpose="Watch this audit move through the pipeline; the report link lands here.",
            show_tour=False,
        )


@router.get("/audits/{audit_id}/progress/partial", response_class=HTMLResponse)
def audit_progress_partial(
    request: Request, audit_id: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """The polled fragment. Ownership re-checked on EVERY poll (§5d — the
    page not being yours must fail here too, not only at first render)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        audit = _owned_audit(session, user, audit_id)
        return _render(
            request,
            "app/_audit_progress.html",
            audit=audit,
            stages=_theater_stages(audit),
            rejected=_rejected_rows(audit),
        )


@router.get("/audits/{audit_id}/row-errors", response_model=None)
def audit_row_errors(
    request: Request, audit_id: str, user_email: str = Depends(current_user)
) -> FileResponse:
    """The validator's rejects, as the CSV the pipeline already wrote."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        audit = _owned_audit(session, user, audit_id)
        if not audit.upload_path:
            raise HTTPException(status_code=404, detail="row errors purged with the upload")
        path = Path(audit.upload_path).parent / "row_errors.csv"
        if not path.exists():
            raise HTTPException(status_code=404, detail="no rows were rejected")
        return FileResponse(path, media_type="text/csv", filename=f"row-errors-{audit_id[:8]}.csv")


@router.get("/findings", response_class=HTMLResponse)
def findings_page(
    request: Request, sort: str = "impact", user_email: str = Depends(current_user)
) -> HTMLResponse:
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
                # plain words at headline depth; the raw codes stay internal
                "severity_label": {"high": "High", "med": "Medium", "low": "Low"}.get(
                    r.severity, r.severity
                ),
                "confidence": r.confidence,
                "confidence_label": {
                    "estimated": "Estimate",
                    "conservative": "Conservative floor",
                }.get(r.confidence, r.confidence),
                "monthly_usd": round(float(r.monthly_impact_usd), 2),
                "verdict": verdicts.get(r.finding_id),
            }
            for r in rows
        ]
        sort_key = sort if sort in SORTS else "impact"
        items.sort(key=SORTS[sort_key])
        ctx = _shell_ctx(session, request, user, "findings")
        return _render(
            request,
            "app/findings.html",
            items=items,
            sort=sort_key,
            audit=audit,
            # why the page looks the way it does — never "connect a source" when
            # an audit actually ran (founder incident 2026-07-22)
            clarity=metrics.audit_clarity(session, request.app.state.pricing_table, user.id),
            support_email=request.app.state.settings.support_email,
            show_tour=False,
            **ctx,
        )


def _drawer_context(
    session: Session, request: Request, user: User, audit_id: str, finding_id: str
) -> dict[str, object]:
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
    if fb is None:
        # The same route re-appears in later audits until it is fixed. Show
        # the verdict already recorded for that route so the customer is not
        # invited to "apply" the same fix again (V-D4 cold-review f.3).
        fb = _verdict_for_route(session, user.id, row)
    detector_help = help_registry.detector(row.detector, request.app.state.settings)
    return {
        "row": row,
        "audit": audit,
        "h": detector_help,
        "verdict": fb.verdict if fb else None,
    }


@router.get("/findings/{audit_id}/{finding_id}", response_class=HTMLResponse)
def finding_drawer(
    request: Request, audit_id: str, finding_id: str, user_email: str = Depends(current_user)
) -> HTMLResponse:
    """Depth (c): why → evidence → fix → verify → methodology (R-CLARITY §1).
    Rendered into a right-hand drawer by htmx (familiarity principle)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ctx = _drawer_context(session, request, user, audit_id, finding_id)
        return _render(request, "app/_finding_drawer.html", **ctx)


def _verdict_for_route(session: Session, user_id: str, row: FindingRow) -> FindingFeedback | None:
    """Latest verdict recorded for this (detector, route) across the user's
    audits — route identity, the same key R-Q9 credits on."""
    key = (row.detector, row.route or row.finding_id)
    audit_ids = [
        a.id for a in session.execute(select(Audit).where(Audit.user_id == user_id)).scalars().all()
    ]
    rows = (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    )
    same_route = {
        (f.audit_id, f.finding_id) for f in rows if (f.detector, f.route or f.finding_id) == key
    }
    candidates = [
        fb
        for fb in session.execute(
            select(FindingFeedback).where(FindingFeedback.audit_id.in_(audit_ids))
        )
        .scalars()
        .all()
        if (fb.audit_id, fb.finding_id) in same_route
    ]
    return max(candidates, key=lambda fb: fb.ts) if candidates else None


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
        # Two callers, two honest answers. The findings drawer targets itself
        # (#w-savings does not exist on that page — targeting it made htmx
        # abort before the request, so verdicts silently never recorded); it
        # gets the refreshed drawer showing the verdict it just cast. The
        # dashboard's widget form keeps the signature moment: the applied fix
        # visibly flows into the headline (R-DESIGN-ADDENDUM 2a).
        if request.headers.get("HX-Target") == "drawer":
            ctx = _drawer_context(session, request, user, audit_id, finding_id)
            return _render(request, "app/_finding_drawer.html", **ctx)
        widget, _ = metrics.savings(session, user.id)
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
