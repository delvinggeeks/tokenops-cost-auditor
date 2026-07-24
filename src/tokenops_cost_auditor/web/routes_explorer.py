"""FR-32 report explorer (R-EXPLORER, founder order 2026-07-23).

SSR only: the filter form is a plain GET and the URL is the whole state —
shareable, bookmarkable, and already the exact shape a saved view will
persist when that slice ships. The finding drawer reuses the shipped
/findings/{audit}/{finding} htmx endpoint — one component, two surfaces.

Copy discipline: filter options and rows carry the registry's plain
phrasing; detector ids stay in form values and drawers (R-PERSONA).
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from tokenops_cost_auditor.api.routes_upload import current_user
from tokenops_cost_auditor.persistence.models import SavedView, User
from tokenops_cost_auditor.persistence.repo import get_or_create_user, workspace_id_for
from tokenops_cost_auditor.services.dashboard import explorer
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE
from tokenops_cost_auditor.web import help as help_registry
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx

MAX_SAVED_VIEWS = 20

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
        # Cover the option list AND every rendered row, so the template can
        # index directly — a missing registry key fails loud (T-HELP law)
        # instead of leaking a raw detector id at headline depth (ux f.1).
        detector_keys = set(view.detector_options) | {
            str(item["detector"]) for item in view.findings
        }
        detector_labels = {key: help_registry.detector_plain(key) for key in detector_keys}
        # O-1: SavedView stays USER-scoped everywhere (list/save/delete). Its
        # write path has a per-user uniqueness constraint (uq_saved_view_user_
        # name) AND a per-user cap, so a saved view is a PERSONAL filter bookmark,
        # not shared workspace data — each member keeps their own regardless of
        # workspace. (The workspace_id column O-0 stamped is reserved for a
        # possible future shared "team views" feature — BACKLOG, not O-1.)
        saved = (
            session.execute(
                select(SavedView).where(SavedView.user_id == user.id).order_by(SavedView.name)
            )
            .scalars()
            .all()
        )
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
            saved_views=saved,
            current_query=explorer.serialize_filters(filters),
            show_tour=False,
            **ctx,
        )


@router.post("/explore/views", response_model=None)
def save_view(
    request: Request,
    name: str = Form(...),
    params: str = Form(""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """FR-32 C3: save the current slice under a name. The stored params are
    parse_filters -> serialize_filters round-tripped, so only whitelisted
    filter keys can ever persist. Same name = replace (a view is a bookmark,
    not a ledger). Export stays HELD on the registered data-export trigger."""
    label = name.strip()[:80]
    if not label:
        raise HTTPException(status_code=400, detail="name required")
    canonical = explorer.serialize_filters(explorer.parse_filters(dict(parse_qsl(params))))
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        # Lock the user row so concurrent saves serialize on the count AND on
        # the same-name upsert (cold-review C3 f.1/f.2 — the G-V1 f.1 bug
        # class from routes_sources, not reintroduced twice). Row lock on
        # Postgres; no-op on SQLite.
        session.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        existing = session.execute(
            select(SavedView).where(SavedView.user_id == user.id, SavedView.name == label)
        ).scalar_one_or_none()
        if existing is not None:
            existing.params = canonical
        else:
            count = len(
                session.execute(select(SavedView).where(SavedView.user_id == user.id))
                .scalars()
                .all()
            )
            if count >= MAX_SAVED_VIEWS:
                raise HTTPException(
                    status_code=400,
                    detail=f"{MAX_SAVED_VIEWS} saved views is the limit — delete one first",
                )
            session.add(
                SavedView(
                    user_id=user.id,
                    workspace_id=workspace_id_for(session, user.id),  # O-0
                    name=label,
                    params=canonical,
                )
            )
        session.commit()
    return RedirectResponse(f"/explore?{canonical}", status_code=303)


@router.post("/explore/views/{view_id}/delete", response_model=None)
def delete_view(
    request: Request, view_id: int, user_email: str = Depends(current_user)
) -> RedirectResponse:
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        row = session.get(SavedView, view_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="saved view not found")
        session.delete(row)
        session.commit()
    return RedirectResponse("/explore", status_code=303)
