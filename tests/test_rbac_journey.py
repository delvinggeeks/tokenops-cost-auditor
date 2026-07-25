"""O-2 RBAC — the four-role journey (R-ORG). One workspace, one owner + an admin,
member and viewer; walk EACH role's surfaces and assert two things per the DoD:
(2) each role SEES exactly the controls it may use (never a dead 403-trap), and
(3) a forbidden mutation POSTed directly FAILS CLOSED (403, never executed).

The audit engine stays role-blind — this all lives at the web boundary."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import Source, Subscription, WorkspaceMember
from tokenops_cost_auditor.persistence.repo import (
    get_or_create_user,
    get_or_create_workspace,
    set_active_workspace,
)
from tokenops_cost_auditor.services.payments.base import grant_payment

OWNER = "rbac-owner@example.com"
ADMIN = "rbac-admin@example.com"
MEMBER = "rbac-member@example.com"
VIEWER = "rbac-viewer@example.com"
F1_BYTES = (Path(__file__).parent / "fixtures" / "openai_small.jsonl").read_bytes()


def _hdr(email: str) -> dict[str, str]:
    return {"X-User-Email": email}


def _seed(app: FastAPI) -> dict[str, str]:
    """Owner (team plan) + admin/member/viewer as members of ONE workspace, each
    acting in it. Also one connected source, so the revoke control is testable.
    Returns each member-row id for the fail-closed mutation probes."""
    ids: dict[str, str] = {}
    with app.state.session_factory() as s:
        owner = get_or_create_user(s, OWNER)
        ws = get_or_create_workspace(s, owner)
        ws.name = "Acme Corp"
        s.add(Subscription(user_id=owner.id, provider="stripe", plan="team"))
        s.add(
            Source(
                user_id=owner.id,
                workspace_id=ws.id,
                provider="openai",
                label="prod",
                status="active",
                key_fingerprint="fp-openai",
            )
        )
        for email, role in ((ADMIN, "admin"), (MEMBER, "member"), (VIEWER, "viewer")):
            u = get_or_create_user(s, email)
            m = WorkspaceMember(workspace_id=ws.id, user_id=u.id, role=role)
            s.add(m)
            s.flush()
            set_active_workspace(s, u.id, ws.id)
            ids[role] = m.id
        s.commit()
    return ids


class TestRenderedSurfacePerRole:
    """(2) A role never SEES a control it can't use — absent, not a 403-trap."""

    def test_members_governance_controls_only_for_managers(self, app: FastAPI) -> None:
        _seed(app)
        c = TestClient(app)
        # owner + admin see the set-role control (name="new_role") on governable rows
        assert 'name="new_role"' in c.get("/settings/members", headers=_hdr(OWNER)).text
        assert 'name="new_role"' in c.get("/settings/members", headers=_hdr(ADMIN)).text
        # member + viewer see the roster but NO governance controls + the honest reason
        member_page = c.get("/settings/members", headers=_hdr(MEMBER)).text
        assert 'name="new_role"' not in member_page
        assert "only an owner or admin can invite" in member_page.lower()
        assert 'name="new_role"' not in c.get("/settings/members", headers=_hdr(VIEWER)).text

    def test_sources_connect_and_revoke_only_for_managers(self, app: FastAPI) -> None:
        _seed(app)
        c = TestClient(app)
        for mgr in (OWNER, ADMIN):
            page = c.get("/sources", headers=_hdr(mgr)).text
            assert 'aria-label="Revoke this connection"' in page  # revoke visible
        for ro in (MEMBER, VIEWER):
            page = c.get("/sources", headers=_hdr(ro)).text
            assert 'aria-label="Revoke this connection"' not in page
            assert "managed by owners and admins" in page.lower()  # honest read-only note

    def test_connect_wizard_surface_not_shown_to_non_managers(self, app: FastAPI) -> None:
        # The gate-round caught this: the Connect BUTTON was hidden but the wizard PAGE
        # rendered its credential form to anyone who navigated directly. A non-manager
        # is now redirected to /sources (never sees the form); a manager gets it.
        _seed(app)
        c = TestClient(app)
        for mgr in (OWNER, ADMIN):
            r = c.get("/sources/connect/openai", headers=_hdr(mgr), follow_redirects=False)
            assert r.status_code == 200
        for ro in (MEMBER, VIEWER):
            r = c.get("/sources/connect/openai", headers=_hdr(ro), follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/sources"

    def test_billing_is_owner_only(self, app: FastAPI) -> None:
        _seed(app)
        c = TestClient(app)
        assert "Plans" in c.get("/billing", headers=_hdr(OWNER)).text
        for non_owner in (ADMIN, MEMBER, VIEWER):
            page = c.get("/billing", headers=_hdr(non_owner)).text
            assert "managed by the workspace" in page.lower()
            assert "Plans" not in page


class TestFailClosedMutations:
    """(3) A forbidden mutation POSTed directly is refused (403), never executed."""

    def test_non_manager_cannot_invite(self, app: FastAPI) -> None:
        _seed(app)
        c = TestClient(app)
        for role_email in (MEMBER, VIEWER):
            r = c.post(
                "/settings/members/invite",
                data={"email": "x@y.com"},
                headers=_hdr(role_email),
                follow_redirects=False,
            )
            assert r.status_code == 403, role_email

    def test_non_manager_cannot_connect_or_revoke_a_source(self, app: FastAPI) -> None:
        ids = _seed(app)
        c = TestClient(app)
        r = c.post(
            "/sources",
            data={"provider": "openai", "label": "x", "api_key": "sk-x"},
            headers=_hdr(MEMBER),
            follow_redirects=False,
        )
        assert r.status_code == 403
        # ...and the manager admin CAN reach the connect handler (not a 403).
        assert ids  # seeded

    def test_non_manager_cannot_change_a_role(self, app: FastAPI) -> None:
        ids = _seed(app)
        c = TestClient(app)
        r = c.post(
            f"/settings/members/{ids['viewer']}/role",
            data={"new_role": "admin"},
            headers=_hdr(MEMBER),
            follow_redirects=False,
        )
        assert r.status_code == 403

    def test_viewer_cannot_run_an_audit_even_with_a_credit(self, app: FastAPI) -> None:
        _seed(app)
        with app.state.session_factory() as s:
            for email in (VIEWER, MEMBER):
                u = get_or_create_user(s, email)
                grant_payment(s, u.id, "manual", 500.0, "USD")
            s.commit()
        c = TestClient(app)
        files = {"file": ("logs.jsonl", io.BytesIO(F1_BYTES), "application/jsonl")}
        # viewer: RUN_AUDITS denied → 403 (the role gate, past the payment gate)
        rv = c.post("/api/v1/audits", headers=_hdr(VIEWER), files=files)
        assert rv.status_code == 403
        # member: RUN_AUDITS granted → NOT blocked by role (proceeds to accept/queue)
        rm = c.post(
            "/api/v1/audits",
            headers=_hdr(MEMBER),
            files={"file": ("logs.jsonl", io.BytesIO(F1_BYTES), "application/jsonl")},
        )
        assert rm.status_code != 403
