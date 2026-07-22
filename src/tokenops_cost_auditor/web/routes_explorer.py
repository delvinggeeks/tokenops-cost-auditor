"""FR-32 report explorer (R-EXPLORER, founder order 2026-07-23).

SSR only: the filter form is a plain GET and the URL is the whole state —
shareable, bookmarkable, and already the exact shape a saved view will
persist when that slice ships. The finding drawer reuses the shipped
/findings/{audit}/{finding} htmx endpoint — one component, two surfaces.

Copy discipline: filter options and rows carry the registry's plain
phrasing; detector ids stay in form values and drawers (R-PERSONA).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.dashboard import explorer
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE
from tokenops_cost_auditor.web import help as help_registry
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

router = APIRouter(tags=["explorer"])

SEVERITY_LABELS = {"high": "High", "med": "Medium", "low": "Low"}
STATUS_LABELS = {
    "applied": "Applied",
    "dismissed": "Dismissed",
    "not_relevant": "Not relevant",
    "unreviewed": "Not reviewed",
}


@router.get("/explore", response_class=HTMLResponse)
def explore_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        filters = explorer.parse_filters(dict(request.query_params))
        view = explorer.compose(session, user.id, filters)
        # Plain phrasing for the finding-type select and rows (jargon law).
        detector_labels = {key: help_registry.detector_plain(key) for key in view.detector_options}
        ctx = _shell_ctx(session, request, user, "explore")
        return _render(
            request,
            "app/explore.html",
            view=view,
            f=filters,
            detector_labels=detector_labels,
            severity_labels=SEVERITY_LABELS,
            status_labels=STATUS_LABELS,
            equiv_line=EQUIV_SPEND_LINE,
            show_tour=False,
            **ctx,
        )
