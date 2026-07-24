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
