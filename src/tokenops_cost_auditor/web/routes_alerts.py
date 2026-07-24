"""Alerts settings + history (PLAN-V15 WP-3b).

Grouped form, saved in one submit — the boring, pre-learned shape
(R-CLARITY §2 familiarity principle).

OBSERVE ONLY: this page configures what reaches the customer by email. It
cannot pause, cap or throttle anything (X-02).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import AlertEvent, AlertRule
from tokenops_cost_auditor.persistence.repo import (
    active_workspace_id,
    get_or_create_user,
    workspace_id_for,
)
from tokenops_cost_auditor.services.alerts import dispatch
from tokenops_cost_auditor.services.alerts.rules import RULE_LABELS, RULES
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.payments import plans
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx
from tokenops_cost_auditor.web.routes_sources import user_plan

router = APIRouter(prefix="/alerts", tags=["alerts"])

UNITS = {
    "spend_spike_dod": "%",
    "waste_above_target": "%",
    "soft_budget": "$ / month",
    "new_high_finding": "",
}
HINTS = {
    "spend_spike_dod": "Tell me when my run-rate jumps by at least this much.",
    "waste_above_target": "Tell me when avoidable spend goes above this share.",
    "new_high_finding": "Tell me as soon as a new high-impact finding appears.",
    "soft_budget": "Tell me when my run-rate passes this figure. Nothing is paused.",
}


def _plan_watches(session: Session, settings: Settings, user_id: str) -> bool:
    """The web-layer edge of the ONE watching rule (dispatch.plan_watches)."""
    return dispatch.plan_watches(settings, user_plan(session, user_id))


def _default_threshold(settings: object, rule: str) -> float | None:
    if rule == "spend_spike_dod":
        return float(getattr(settings, "alert_spend_spike_dod_pct", 30.0))
    if rule == "waste_above_target":
        return float(getattr(settings, "alert_waste_target_pct", 25.0))
    return None


@router.get("", response_class=HTMLResponse)
def alerts_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        # §5a: a capability the plan lacks is OMITTED from the payload — the
        # rules/threshold data never reaches the template, which renders an
        # honest upsell in its place. Not a disabled form: nothing is watching
        # on this plan, and a grey form would imply something is.
        watches = _plan_watches(session, settings, user.id)
        ws = active_workspace_id(session, user.id)
        rules = None
        if watches:
            # O-1: display the WORKSPACE's alert rules — members see what is
            # armed. (Editing them, save_alerts below, stays owner-scoped until
            # O-2 RBAC; the AlertEvent history stays user-scoped — no column.)
            configured = {
                r.rule: r
                for r in session.execute(select(AlertRule).where(AlertRule.workspace_id == ws))
                .scalars()
                .all()
            }
            rules = [
                {
                    "key": key,
                    "label": RULE_LABELS[key],
                    "hint": HINTS[key],
                    "unit": UNITS[key],
                    "enabled": key in configured and configured[key].enabled,
                    "threshold": (
                        configured[key].threshold
                        if key in configured
                        else _default_threshold(settings, key)
                    ),
                }
                for key in RULES
            ]
        # O-1: AlertEvent has no workspace_id (O-1b deferral) — the fired-alert
        # history stays user-scoped (each member sees their own notifications).
        history = (
            session.execute(
                select(AlertEvent)
                .where(AlertEvent.user_id == user.id)
                .order_by(AlertEvent.ts.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        currency = plans.viewer_currency(
            session,
            user.id,
            request.query_params.get("ccy"),
            request.headers.get("accept-language", ""),
            request.cookies.get("ccy"),
        )
        ctx = _shell_ctx(session, request, user, "alerts")
        return _render(
            request,
            "app/alerts.html",
            rules=rules,
            history=history,
            labels=RULE_LABELS,
            # §5b honest upsell: what unlocks it and what that costs, in the
            # viewer's ONE currency (R-PRICING-FINAL-2), no dark patterns.
            unlock_plan=None if watches else plans.get(settings, plans.PRO),
            currency=currency,
            launch_open=plans.launch_open(session, settings, currency),
            show_tour=False,
            **ctx,
        )


@router.post("", response_model=None)
async def save_alerts(
    request: Request, user_email: str = Depends(current_user)
) -> RedirectResponse:
    form = await request.form()
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # §5d: the form not being rendered is not authority — this is. A plan
        # without scheduled audits has nothing evaluating rules, so accepting
        # the save would store configuration that silently does nothing.
        if not _plan_watches(session, request.app.state.settings, user.id):
            raise HTTPException(
                status_code=403,
                detail="alerts are part of the Pro plan — nothing is watching on this plan",
            )
        # O-1: saving rules is a MUTATE — stays owner-scoped (fail-closed until
        # O-2 RBAC). Members SEE the workspace's rules (alerts_page) but editing
        # them is an owner action for now.
        existing = {
            r.rule: r
            for r in session.execute(select(AlertRule).where(AlertRule.user_id == user.id))
            .scalars()
            .all()
        }
        for key in RULES:
            enabled = form.get(f"{key}_enabled") is not None
            raw = str(form.get(f"{key}_threshold") or "").strip()
            try:
                threshold: float | None = float(raw) if raw else None
            except ValueError:
                threshold = None  # unparseable input falls back to the default
            if threshold is not None and threshold < 0:
                threshold = None
            row = existing.get(key)
            if row is None:
                session.add(
                    AlertRule(
                        user_id=user.id,
                        workspace_id=workspace_id_for(session, user.id),  # O-0
                        rule=key,
                        threshold=threshold,
                        enabled=enabled,
                    )
                )
            else:
                row.enabled = enabled
                row.threshold = threshold
        auditlog.append(session, user.email, "alerts.updated", user.email)
        session.commit()
    return RedirectResponse("/alerts", status_code=303)
