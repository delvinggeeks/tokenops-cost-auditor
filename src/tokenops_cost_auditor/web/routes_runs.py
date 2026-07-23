"""Runs observatory (WP-PIPELINE-UI): every audit this account ever ran —
what triggered it, how long each stage took, and exactly what each stage
did — plus the pull ledger (every pull, including the failures) and the
alert-check ledger ("checked, nothing crossed" is evidence too).

Counts only everywhere (FR-22). Purged runs stay listed with what remains
(FR-31). Runs that predate stage recording say so instead of pretending.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import (
    AlertCheck,
    Audit,
    FindingRow,
    PullEvent,
    Source,
    StageEvent,
    User,
)
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.alerts.rules import RULE_LABELS
from tokenops_cost_auditor.web import help as help_registry
from tokenops_cost_auditor.web.routes_dashboard import _shell_ctx

router = APIRouter(tags=["runs"])

TRIGGERS = {"subscription": "scheduled pull", "collector": "collector ship"}
STAGE_LABELS = {"ingest": "Ingest", "price": "Price", "detect": "Detect", "report": "Report"}
ARTIFACT_NAMES = {"json": "JSON", "html": "web", "pdf": "PDF"}
LEDGER_CAP = 50  # pulls/alert-checks shown; the cap is STATED, never silent


def _session(request: Request) -> Session:
    session: Session = request.app.state.session_factory()
    return session


def _render(request: Request, template: str, **ctx: object) -> HTMLResponse:
    tpl = request.app.state.jinja.get_template(template)
    return HTMLResponse(tpl.render(help=help_registry, **ctx))


def _as_int(v: object) -> int:
    """JSON detail values arrive as `object`; counts coerce, anything else is 0."""
    return int(v) if isinstance(v, int | float | str) else 0


def _stage_note(stage: str, detail: dict[str, object]) -> str:
    """One honest line per stage cell, built from counts the run recorded."""
    if stage == "ingest":
        rows = _as_int(detail.get("rows"))
        if "rejected" in detail:
            return f"{rows:,} rows · {_as_int(detail.get('rejected')):,} rejected"
        return f"{rows:,} usage buckets · {_as_int(detail.get('days'))} day(s)"
    if stage == "price":
        unpriced = detail.get("unpriced_models") or []
        n = len(unpriced) if isinstance(unpriced, list) else 0
        tail = f"{n} unpriced model(s)" if n else "0 unpriced"
        return f"{_as_int(detail.get('priced_rows')):,} priced · {tail}"
    if stage == "detect":
        detectors = detail.get("detectors") or {}
        n_det = len(detectors) if isinstance(detectors, dict) else 0
        return f"{n_det} detectors ran · {_as_int(detail.get('findings'))} finding(s)"
    if stage == "report":
        arts = detail.get("artifacts") or []
        if isinstance(arts, list) and arts:
            return " + ".join(ARTIFACT_NAMES.get(str(a), str(a)) for a in arts)
    return ""


def _ribbon_stages(events: list[StageEvent]) -> list[dict[str, str]]:
    """StageEvent rows -> the kit ribbon's rich-form mappings, in the order
    the stages actually ran (source audits detect before pricing — the strip
    tells it exactly as it happened)."""
    out: list[dict[str, str]] = []
    for ev in events:
        secs = (
            (ev.finished_at - ev.started_at).total_seconds() if ev.finished_at is not None else None
        )
        out.append(
            {
                "label": STAGE_LABELS.get(ev.stage, ev.stage.title()),
                "value": f"{secs:.1f}s" if secs is not None else "—",
                "note": _stage_note(ev.stage, dict(ev.detail or {})),
                "state": "active",
            }
        )
    return out


def _runs_view(session: Session, user: User) -> dict[str, object]:
    audits = (
        session.execute(
            select(Audit).where(Audit.user_id == user.id).order_by(Audit.created_at.desc())
        )
        .scalars()
        .all()
    )
    events = (
        session.execute(
            select(StageEvent)
            .join(Audit, StageEvent.audit_id == Audit.id)
            .where(Audit.user_id == user.id)
            .order_by(StageEvent.started_at)
        )
        .scalars()
        .all()
    )
    events_by_audit: dict[str, list[StageEvent]] = {}
    for ev in events:
        events_by_audit.setdefault(ev.audit_id, []).append(ev)

    # Per-detector money lines for the drill: findings grouped in ONE query.
    impact_rows = session.execute(
        select(
            FindingRow.audit_id,
            FindingRow.detector,
            func.count(FindingRow.id),
            func.sum(FindingRow.monthly_impact_usd),
        )
        .join(Audit, FindingRow.audit_id == Audit.id)
        .where(Audit.user_id == user.id)
        .group_by(FindingRow.audit_id, FindingRow.detector)
    ).all()
    impact: dict[str, dict[str, tuple[int, float]]] = {}
    for audit_id, detector, n, usd in impact_rows:
        impact.setdefault(audit_id, {})[detector] = (int(n), float(usd or 0.0))

    runs: list[dict[str, object]] = []
    in_flight = False
    for a in audits:
        evs = events_by_audit.get(a.id, [])
        duration = None
        if evs and evs[-1].finished_at is not None:
            duration = (evs[-1].finished_at - evs[0].started_at).total_seconds()
        if a.status in ("queued", "processing"):
            in_flight = True
        detect_detail: dict[str, object] = {}
        rejected = 0
        for ev in evs:
            if ev.stage == "detect":
                detect_detail = dict(ev.detail or {})
            if ev.stage == "ingest":
                rejected = _as_int(dict(ev.detail or {}).get("rejected"))
        detectors_raw = detect_detail.get("detectors")
        detector_lines: list[dict[str, object]] = []
        if isinstance(detectors_raw, dict):
            per_run_impact = impact.get(a.id, {})
            for name, count in detectors_raw.items():
                usd = per_run_impact.get(name, (0, 0.0))[1]
                detector_lines.append({"detector": name, "count": int(count), "monthly_usd": usd})
        runs.append(
            {
                "audit": a,
                "trigger": TRIGGERS.get(a.paid_via or "", "file upload"),
                "duration": f"{duration:.1f}s" if duration is not None else None,
                "stages": _ribbon_stages(evs),
                "detectors": detector_lines,
                "rejected": rejected,
                "purged": a.purged_at is not None,
                "has_upload": bool(a.upload_path),
            }
        )

    pull_total = session.execute(
        select(func.count(PullEvent.id))
        .join(Source, PullEvent.source_id == Source.id)
        .where(Source.user_id == user.id)
    ).scalar_one()
    pulls = session.execute(
        select(PullEvent, Source)
        .join(Source, PullEvent.source_id == Source.id)
        .where(Source.user_id == user.id)
        .order_by(PullEvent.ts.desc())
        .limit(LEDGER_CAP)
    ).all()

    check_total = session.execute(
        select(func.count(AlertCheck.id)).where(AlertCheck.user_id == user.id)
    ).scalar_one()
    checks = (
        session.execute(
            select(AlertCheck)
            .where(AlertCheck.user_id == user.id)
            .order_by(AlertCheck.ts.desc())
            .limit(LEDGER_CAP)
        )
        .scalars()
        .all()
    )

    return {
        "runs": runs,
        "in_flight": in_flight,
        "pulls": [{"event": ev, "source": src} for ev, src in pulls],
        "pull_total": pull_total,
        "checks": checks,
        "check_total": check_total,
        "rule_labels": RULE_LABELS,
        "cap": LEDGER_CAP,
    }


@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ctx = _shell_ctx(session, request, user, "runs")
        return _render(request, "app/runs.html", view=_runs_view(session, user), **ctx)


@router.get("/runs/partial", response_class=HTMLResponse)
def runs_partial(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """The self-polled runs ledger while a run is in flight (same law as the
    pipeline widget: the swap that catches the landing drops the trigger, and
    idle pages make zero polling requests)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        return _render(
            request, "app/_runs_ledger.html", view=_runs_view(session, user), standalone=True
        )
