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
)
from tokenops_cost_auditor.persistence.repo import (
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
