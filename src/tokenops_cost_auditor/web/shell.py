"""Shared app-shell context (O-1b-1, R-ORG).

The workspace bar — the "acting in <workspace>" indicator and the switcher —
must appear on EVERY app page (R-VERTICAL reachability law), but this codebase
builds shell context two ways: the `_shell_ctx` helper (dashboard, runs,
settings, …) and manual `tpl.render(...)` calls (sources, developer, upload,
connect wizard). Both call this ONE function, so the indicator can never be
present on some pages and missing on others.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.repo import active_workspace_id, list_memberships


def workspace_bar(session: Session, user_id: str) -> dict[str, object]:
    """Topbar context: the workspaces the user belongs to (switcher options,
    each with role + whether it is active) and the active workspace's name.

    `active_workspace_id` is authoritative and leak-safe (it validates live
    membership and falls back to the personal workspace), so the "active" flag
    and the name always agree with what every read on the page is scoped to.
    A user with a single workspace yields a one-item list — the template shows
    a plain indicator with no switch control (honest solo state, no dead UI)."""
    active_ws = active_workspace_id(session, user_id)
    workspaces = [
        {"id": ws.id, "name": ws.name, "role": role, "active": ws.id == active_ws}
        for ws, role in list_memberships(session, user_id)
    ]
    active_ws_name = next((w["name"] for w in workspaces if w["active"]), "")
    return {"workspaces": workspaces, "active_workspace_name": active_ws_name}


def data_freshness(session: Session, user_id: str) -> dict[str, object]:
    """The topbar 'Data as of …' string PLUS the honest 'nothing is connected'
    state — shared by `_shell_ctx` AND the manual-render pages (the workspace_bar
    pattern) so every page agrees on how fresh the figures are.

    The load-bearing case (founder 2026-07-24 walkthrough): a workspace with a
    past audit but NO live feed. The Sources page shows 'nothing connected' while
    Overview/Findings keep rendering the last audit's real numbers — which reads
    as stale/live. Here `sources_disconnected` turns True so the shell banner and
    the freshness line both say the figures are HISTORY until something reconnects.
    Cheap: the feed check runs only when an audit exists (the common empty path
    returns immediately)."""
    from tokenops_cost_auditor.services.dashboard import metrics

    latest = metrics.latest_audit(session, user_id)
    if latest is None:
        return {
            "freshness": "No data yet — connect a source or upload a log file",
            "sources_disconnected": False,
            "data_as_of": "",
        }
    when = latest.report_ready_at or latest.created_at
    as_of = f"{when:%Y-%m-%d %H:%M} UTC"
    disconnected = not metrics.has_live_feed(session, user_id)
    freshness = f"Data as of {as_of}" + (" · nothing connected" if disconnected else "")
    return {"freshness": freshness, "sources_disconnected": disconnected, "data_as_of": as_of}
