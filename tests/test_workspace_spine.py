"""O-0 tests (R-ORG) — the workspace tenancy spine.

Load-bearing pins: every user becomes a workspace-of-one (owner); the write-path
stamps workspace_id on the resources it creates; two workspaces are DISTINCT and
a workspace-scoped query cannot see another's rows (the O-0 DoD, correct while
1 user = 1 workspace); the owner-only rename journey; and that the engine stays
tenant-blind (services/rules + services/pricing never import workspaces).
"""

from __future__ import annotations

import json
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    IngestKey,
    Subscription,
    User,
    Workspace,
    WorkspaceMember,
    utcnow,
)
from tokenops_cost_auditor.persistence.repo import (
    active_workspace_id,
    create_audit,
    get_or_create_user,
    get_or_create_workspace,
    workspace_id_for,
)

EMAIL = "ws-owner@example.com"
OTHER = "ws-other@example.com"
HDR = {"X-User-Email": EMAIL}
OTHER_HDR = {"X-User-Email": OTHER}


def _workspace_of(session, user_id: str) -> Workspace | None:
    return session.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.role == "owner")
    )


class TestWorkspaceCreation:
    def test_new_user_becomes_workspace_of_one(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            ws = _workspace_of(s, user.id)
            assert ws is not None and ws.personal is True
            assert ws.name == f"{EMAIL}'s workspace"
            wm = s.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
            assert wm is not None and wm.role == "owner" and wm.workspace_id == ws.id

    def test_get_or_create_workspace_is_idempotent(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            w1 = get_or_create_workspace(s, user)
            w2 = get_or_create_workspace(s, user)
            s.commit()
            assert w1.id == w2.id
            assert s.scalar(select(func.count()).select_from(Workspace)) == 1

    def test_second_owner_membership_rejected_by_db(self, app: FastAPI) -> None:
        """cold-reviewer O-0 f.1: the workspace-of-one 1:1 invariant is a DB FACT.
        A second owner membership for the same user — the shape a racy self-heal
        would produce — is rejected by uq_owner_membership_per_user, so the user
        can never end up with two personal workspaces."""
        import pytest
        from sqlalchemy.exc import IntegrityError

        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            second = Workspace(name="sneaky second", personal=True)
            s.add(second)
            s.flush()
            s.add(WorkspaceMember(workspace_id=second.id, user_id=user.id, role="owner"))
            with pytest.raises(IntegrityError):
                s.commit()


class TestActiveWorkspaceResolver:
    def test_active_workspace_is_the_personal_one_in_o1a(self, app: FastAPI) -> None:
        """O-1a: active_workspace_id resolves to the user's personal workspace,
        so re-scoping reads from user_id to it is behavior-preserving under 1:1.
        (O-1b makes it the switchable active workspace.)"""
        from tokenops_cost_auditor.persistence.repo import active_workspace_id

        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            assert active_workspace_id(s, user.id) == workspace_id_for(s, user.id)
            assert active_workspace_id(s, user.id) is not None


class TestWritePathStamps:
    def test_audit_stamped_with_owner_workspace(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            wsid = workspace_id_for(s, user.id)
            audit = create_audit(s, user.id)
            s.commit()
            assert wsid is not None and audit.workspace_id == wsid

    def test_ingest_key_stamped_via_route(self, app: FastAPI) -> None:
        # grant Pro, mint an ingest key through the real route, assert stamped
        client = TestClient(app)
        client.get("/settings", headers=HDR)  # create user + workspace
        with app.state.session_factory() as s:
            user = s.scalar(select(User).where(User.email == EMAIL))
            s.add(Subscription(user_id=user.id, provider="stripe", plan="pro"))
            s.commit()
            wsid = workspace_id_for(s, user.id)
        resp = client.post("/sources/sdk/key", data={"label": "prod"}, headers=HDR)
        assert resp.status_code == 200
        with app.state.session_factory() as s:
            key = s.scalar(select(IngestKey))
            assert key is not None and key.workspace_id == wsid


class TestIsolation:
    def test_two_workspaces_distinct_and_invisible(self, app: FastAPI) -> None:
        """O-0 DoD: workspace B's rows are invisible to a query scoped to A."""
        with app.state.session_factory() as s:
            ua = get_or_create_user(s, EMAIL)
            ub = get_or_create_user(s, OTHER)
            s.commit()
            wa, wb = workspace_id_for(s, ua.id), workspace_id_for(s, ub.id)
            assert wa is not None and wb is not None and wa != wb
            audit_a = create_audit(s, ua.id)
            audit_b = create_audit(s, ub.id)
            s.commit()
            assert audit_a.workspace_id == wa and audit_b.workspace_id == wb
            # a workspace-scoped read sees ONLY its own rows
            in_a = s.scalars(select(Audit.id).where(Audit.workspace_id == wa)).all()
            assert list(in_a) == [audit_a.id]
            assert audit_b.id not in in_a


class TestReadScopeSweep:
    """O-1 (R-ORG) — the read re-scope. Reads flow through active_workspace_id
    + workspace_id so a workspace's members see the same data (O-1b) while
    cross-tenant isolation holds. Behavior-preserving while 1 user = 1
    workspace; pinned so a wrong OR MISSED re-scope regresses a test."""

    def test_active_workspace_id_ensure_creates_and_is_never_none(self, app: FastAPI) -> None:
        """LEAK-SAFETY: active_workspace_id must never hand a read None — a
        `Model.workspace_id == None` renders IS NULL and would match every
        tenant's un-stamped rows. A user with no owner membership (the
        out-of-band shape) is self-healed to a real workspace, not left None."""
        from sqlalchemy import delete

        from tokenops_cost_auditor.persistence.repo import active_workspace_id

        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            # Strip the workspace to simulate a User minted out-of-band (Core
            # DML bypasses the conftest fixture-stamp hook).
            s.execute(delete(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
            s.execute(delete(Workspace))
            s.commit()
            assert workspace_id_for(s, user.id) is None
            wsid = active_workspace_id(s, user.id)  # ensure-creates
            assert wsid is not None
            assert workspace_id_for(s, user.id) == wsid  # and it persisted

    def test_get_user_audit_is_workspace_scoped(self, app: FastAPI) -> None:
        """The EMAIL-based ownership check (grep-missed by the `.user_id ==`
        inventory) now scopes to the active workspace: visible to its workspace,
        an identical 404-equiv (None) to another — no existence oracle."""
        from tokenops_cost_auditor.persistence.repo import get_user_audit

        with app.state.session_factory() as s:
            ua = get_or_create_user(s, EMAIL)
            get_or_create_user(s, OTHER)
            s.commit()
            aid = create_audit(s, ua.id).id
            s.commit()
        with app.state.session_factory() as s:
            assert get_user_audit(s, aid, EMAIL) is not None
            assert get_user_audit(s, aid, OTHER) is None

    def test_null_workspace_audit_never_matches_a_workspace_read(self, app: FastAPI) -> None:
        """A pre-O-0-shaped audit (workspace_id IS NULL) must never surface
        through a workspace-scoped read — proves `== ws` cannot become IS NULL
        (ws is never None). Forced un-stamped via Core UPDATE (bypasses the
        fixture-stamp hook) so even the OWNER cannot reach it."""
        from sqlalchemy import update

        from tokenops_cost_auditor.persistence.repo import get_user_audit

        with app.state.session_factory() as s:
            ua = get_or_create_user(s, EMAIL)
            s.commit()
            aid = create_audit(s, ua.id).id
            s.execute(update(Audit).where(Audit.id == aid).values(workspace_id=None))
            s.commit()
            assert get_user_audit(s, aid, EMAIL) is None

    def test_rescoped_service_read_isolates_across_workspaces(self, app: FastAPI) -> None:
        """A representative swept read (metrics.latest_audit) returns the
        caller's active-workspace audit and NEVER another workspace's."""
        from tokenops_cost_auditor.services.dashboard import metrics

        with app.state.session_factory() as s:
            ua = get_or_create_user(s, EMAIL)
            ub = get_or_create_user(s, OTHER)
            s.commit()
            a = create_audit(s, ua.id)
            a.status = "done"
            b = create_audit(s, ub.id)
            b.status = "done"
            s.commit()
            la = metrics.latest_audit(s, ua.id)
            lb = metrics.latest_audit(s, ub.id)
            assert la is not None and la.id == a.id
            assert lb is not None and lb.id == b.id
            assert la.id != lb.id  # A's read never returns B's audit


class TestRenameJourney:
    def test_settings_shows_workspace_section(self, app: FastAPI) -> None:
        html = TestClient(app).get("/settings", headers=HDR).text
        squashed = re.sub(r"\s+", " ", html)
        assert 'action="/settings/workspace/rename"' in squashed  # the click path
        assert "workspace of one" in squashed  # honest single-tenant framing

    def test_owner_renames_and_only_theirs_changes(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/settings", headers=HDR)  # create EMAIL's workspace
        client.get("/settings", headers=OTHER_HDR)  # create OTHER's workspace
        resp = client.post(
            "/settings/workspace/rename",
            data={"name": "Acme Corp"},
            headers=HDR,
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "Acme Corp" in client.get("/settings", headers=HDR).text
        # a different owner's workspace is untouched (rename is workspace-local)
        assert "Acme Corp" not in client.get("/settings", headers=OTHER_HDR).text

    def test_empty_name_rejected(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/settings", headers=HDR)
        r = client.post("/settings/workspace/rename", data={"name": "   "}, headers=HDR)
        assert r.status_code == 400


class TestEngineStaysTenantBlind:
    def test_rules_and_pricing_never_import_workspaces(self) -> None:
        """R-ORG hard boundary: the audit engine must not learn what a workspace
        is. No source file under services/rules or services/pricing may mention
        Workspace / workspace_id / WorkspaceMember."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent / "src" / "tokenops_cost_auditor"
        for pkg in ("services/rules", "services/pricing"):
            for py in (root / pkg).rglob("*.py"):
                text = py.read_text(encoding="utf-8")
                assert "Workspace" not in text, f"{py} references Workspace"
                assert "workspace_id" not in text, f"{py} references workspace_id"


class TestRegression:
    def test_existing_ingest_journey_still_works(self, app: FastAPI) -> None:
        """A user's upload→audit journey is unchanged by the tenancy layer."""
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        with app.state.session_factory() as s:
            user = s.scalar(select(User).where(User.email == EMAIL))
            s.add(Subscription(user_id=user.id, provider="stripe", plan="pro"))
            s.commit()
        blob = json.dumps(
            {
                "records": [
                    {
                        "ts": "2026-07-20T10:00:00Z",
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "prompt_tokens": 100,
                        "completion_tokens": 10,
                    }
                ]
            }
        )
        # mint an ingest key and post a record — the audit lands, stamped
        key_html = client.post("/sources/sdk/key", data={"label": "k"}, headers=HDR).text
        token = re.search(r"Bearer (ik_[A-Za-z0-9_\-]+)", key_html).group(1)
        resp = client.post(
            "/api/v1/ingest",
            content=blob,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        assert resp.status_code == 201
        with app.state.session_factory() as s:
            user = s.scalar(select(User).where(User.email == EMAIL))
            wsid = workspace_id_for(s, user.id)
            audit = s.scalar(select(Audit).where(Audit.user_id == user.id))
            assert audit is not None and audit.workspace_id == wsid


class TestWorkspaceSwitcherJourney:
    """O-1b-1 (R-ORG) — the workspace switcher, walked as a user. Seeds a user
    into TWO workspaces (membership rows directly) and pins the acceptance
    criteria: the active workspace is shown on the shell; switching flips what
    every read returns; a non-member switch is refused and changes nothing; a
    solo user gets an honest indicator with no dead control; and the indicator
    is reachable on EVERY app page (both _shell_ctx and manual-render)."""

    A_NAME = "Acme-A-Workspace"
    B_NAME = "Shared-Team-B"

    def _seed_two_workspaces(self, app: FastAPI) -> tuple[str, str]:
        """EMAIL owns personal workspace A (renamed, holding a done audit) and is
        a MEMBER of a second workspace B (empty). EMAIL cannot OWN B — they
        already own A and uq_owner_membership_per_user is per user — so B carries
        a member row, exactly the shape O-1b-2 invites will create. Returns
        (a_id, b_id)."""
        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            a = get_or_create_workspace(s, user)
            a.name = self.A_NAME
            s.flush()
            a_id = a.id
            # a done audit lands in A (the caller's active workspace) → the
            # workspace-scoped freshness read says "Data as of ..." for A only.
            audit = create_audit(s, user.id)
            audit.status = "done"
            audit.report_ready_at = utcnow()
            b = Workspace(name=self.B_NAME, personal=False)
            s.add(b)
            s.flush()
            b_id = b.id
            s.add(WorkspaceMember(workspace_id=b_id, user_id=user.id, role="member"))
            s.commit()
            return a_id, b_id

    def test_shell_shows_active_workspace_and_switcher(self, app: FastAPI) -> None:
        self._seed_two_workspaces(app)
        html = re.sub(r"\s+", " ", TestClient(app).get("/dashboard", headers=HDR).text)
        assert self.A_NAME in html  # (1) active-workspace name visible on the shell
        assert "workspace-menu" in html  # (5) switch control is one click away
        assert 'action="/settings/workspace/switch"' in html
        assert self.B_NAME in html  # the other workspace is offered

    def test_switching_flips_every_read(self, app: FastAPI) -> None:
        _a_id, b_id = self._seed_two_workspaces(app)
        client = TestClient(app)
        # active = A: the dashboard reads A's data (a done audit → dated freshness)
        before = client.get("/dashboard", headers=HDR).text
        assert "Data as of" in before and self.A_NAME in before
        # switch to B
        r = client.post(
            "/settings/workspace/switch",
            data={"workspace_id": b_id},
            headers=HDR,
            follow_redirects=False,
        )
        assert r.status_code == 303
        # active = B: EVERY read now scopes to B — the dashboard flips to B's
        # (empty) zero state and the indicator names B; A's data no longer shows.
        after = client.get("/dashboard", headers=HDR).text
        assert self.B_NAME in after
        assert "No data yet" in after
        assert "Data as of" not in after
        with app.state.session_factory() as s:
            user = s.scalar(select(User).where(User.email == EMAIL))
            assert active_workspace_id(s, user.id) == b_id

    def test_switch_to_non_member_refused_and_changes_nothing(self, app: FastAPI) -> None:
        a_id, _b_id = self._seed_two_workspaces(app)
        with app.state.session_factory() as s:
            foreign = Workspace(name="Not-Yours", personal=False)
            s.add(foreign)
            s.commit()
            foreign_id = foreign.id
        r = TestClient(app).post(
            "/settings/workspace/switch",
            data={"workspace_id": foreign_id},
            headers=HDR,
            follow_redirects=False,
        )
        assert r.status_code == 303  # silent no-op; a forged id cannot grant access
        with app.state.session_factory() as s:
            user = s.scalar(select(User).where(User.email == EMAIL))
            assert active_workspace_id(s, user.id) == a_id  # unchanged — never foreign
            assert active_workspace_id(s, user.id) != foreign_id

    def test_solo_user_sees_honest_indicator_no_dead_control(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=OTHER_HDR)  # OTHER: a workspace-of-one
        html = re.sub(r"\s+", " ", client.get("/dashboard", headers=OTHER_HDR).text)
        assert "workspace-solo" in html  # the honest indicator is present...
        assert "workspace-menu" not in html  # ...but there is NO switcher menu...
        assert 'action="/settings/workspace/switch"' not in html  # ...and no dead control

    def test_indicator_reachable_on_every_app_page(self, app: FastAPI) -> None:
        """Reachability law (system-tester gate): the workspace bar is on EVERY
        app-shell page — the _shell_ctx pages AND the manual-render ones — so a
        future edit that drops workspace_bar from one consumer (e.g. billing)
        fails HERE instead of shipping. All 14 shell destinations are walked."""
        self._seed_two_workspaces(app)
        client = TestClient(app)
        pages = (
            "/dashboard",
            "/findings",
            "/explore",
            "/runs",
            "/activity",
            "/guide",
            "/sources",
            "/sources/connect/openai",
            "/upload",
            "/alerts",
            "/statements",
            "/billing",
            "/settings",
            "/settings/developer",
        )
        for path in pages:
            resp = client.get(path, headers=HDR)
            assert resp.status_code == 200, f"{path} -> {resp.status_code}"
            assert self.A_NAME in resp.text, f"workspace indicator missing on {path}"

    def test_workspace_bar_never_empty_ensure_creates(self, app: FastAPI) -> None:
        """cold-review O-1b-1: workspace_bar always yields a NAMED active
        workspace — active_workspace_id ensure-creates the personal workspace +
        membership before list_memberships reads it — so the indicator can never
        silently vanish. Even a user whose rows were stripped out-of-band gets it."""
        from sqlalchemy import delete

        from tokenops_cost_auditor.web.shell import workspace_bar

        with app.state.session_factory() as s:
            user = get_or_create_user(s, EMAIL)
            s.commit()
            s.execute(delete(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
            s.execute(delete(Workspace))
            s.commit()
            bar = workspace_bar(s, user.id)
            assert bar["workspaces"], "workspace_bar must never be empty"
            assert bar["active_workspace_name"], "the active workspace must be named"
            assert any(w["active"] for w in bar["workspaces"])
