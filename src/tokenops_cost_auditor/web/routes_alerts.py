"""Alerts settings + history (PLAN-V15 WP-3b).

Grouped form, saved in one submit — the boring, pre-learned shape
(R-CLARITY §2 familiarity principle).

OBSERVE ONLY: this page configures what reaches the customer by email. It
cannot pause, cap or throttle anything (X-02).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import AlertEvent, AlertRule
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.alerts.rules import RULE_LABELS, RULES
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

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
        configured = {
            r.rule: r
            for r in session.execute(select(AlertRule).where(AlertRule.user_id == user.id))
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
        ctx = _shell_ctx(session, request, user, "alerts")
        return _render(
            request,
            "app/alerts.html",
            rules=rules,
            history=history,
            labels=RULE_LABELS,
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
                    AlertRule(user_id=user.id, rule=key, threshold=threshold, enabled=enabled)
                )
            else:
                row.enabled = enabled
                row.threshold = threshold
        auditlog.append(session, user.email, "alerts.updated", user.email)
        session.commit()
    return RedirectResponse("/alerts", status_code=303)
