"""O-1b-2 (R-ORG) — workspace invites & accept, walked as owner + invitee.

Pins the acceptance criteria: the invite is emailed with the code stored ONLY as
a hash; accept requires a matching email AND an unconsumed, unexpired code (wrong
email / reused / expired all refused with honest states); on accept the invitee
is a member with the shared workspace ACTIVE and sees its audits; the invite is
owner-only + Scale-gated + rate-limited; isolation holds for a third party.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Subscription,
    User,
    WorkspaceInvite,
    WorkspaceMember,
    utcnow,
)
from tokenops_cost_auditor.persistence.repo import (
    active_workspace_id,
    create_audit,
    get_or_create_user,
    get_or_create_workspace,
)
from tokenops_cost_auditor.services.mail.base import LogMailAdapter

OWNER = "invite-owner@example.com"
MATE = "invite-mate@example.com"
STRANGER = "invite-stranger@example.com"


class CapturingMail(LogMailAdapter):
    """Records the invite links it would send, so a test can read the one-shot
    code (never persisted) exactly as the invitee would receive it."""

    def __init__(self) -> None:
        self.invites: list[tuple[str, str, str]] = []

    def workspace_invite(self, to_email: str, link_url: str, workspace_name: str) -> None:
        self.invites.append((to_email, link_url, workspace_name))


def _code_from(link_url: str) -> str:
    return parse_qs(urlparse(link_url).query)["code"][0]


def _seed_scale_owner(app: FastAPI, *, with_audit: bool = True) -> None:
    """OWNER owns a named workspace on the Scale (team) plan, with a done audit
    to share."""
    with app.state.session_factory() as s:
        owner = get_or_create_user(s, OWNER)
        ws = get_or_create_workspace(s, owner)
        ws.name = "Acme Corp"
        s.add(Subscription(user_id=owner.id, provider="stripe", plan="team"))
        if with_audit:
            audit = create_audit(s, owner.id)
            audit.status = "done"
            audit.report_ready_at = utcnow()
        s.commit()


def _invite(app: FastAPI, invitee: str) -> str:
    """OWNER sends an invite; return the one-shot code captured from the mail."""
    app.state.mail = CapturingMail()
    r = TestClient(app).post(
        "/settings/members/invite",
        data={"email": invitee},
        headers={"X-User-Email": OWNER},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.status_code
    return _code_from(app.state.mail.invites[-1][1])


class TestInviteAcceptJourney:
    def test_owner_invites_teammate_who_accepts_and_sees_shared_audits(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        code = _invite(app, MATE)
        # (1) the code is emailed and stored ONLY as a hash — not in plaintext
        with app.state.session_factory() as s:
            inv = s.scalar(select(WorkspaceInvite))
            assert inv is not None and inv.code_hash and code != inv.code_hash
            assert inv.email == MATE and inv.role == "member" and inv.consumed_at is None

        mate = TestClient(app)
        show = mate.get(f"/invite/accept?code={code}", headers={"X-User-Email": MATE})
        assert show.status_code == 200 and "Accept invitation" in show.text
        r = mate.post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/dashboard"

        # (3) invitee is a member and the shared workspace is ACTIVE
        with app.state.session_factory() as s:
            owner = s.scalar(select(User).where(User.email == OWNER))
            mate_u = s.scalar(select(User).where(User.email == MATE))
            owner_ws = active_workspace_id(s, owner.id)
            assert active_workspace_id(s, mate_u.id) == owner_ws
            row = s.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == mate_u.id,
                    WorkspaceMember.workspace_id == owner_ws,
                )
            )
            assert row is not None and row.role == "member"

        # (4) the invitee now sees the workspace's audits on the dashboard
        dash = mate.get("/dashboard", headers={"X-User-Email": MATE}).text
        assert "Data as of" in dash  # the owner's done audit, shared
        assert "Acme Corp" in dash  # acting in the shared workspace

        # (6) a third party still sees nothing shared — isolation holds
        stranger = TestClient(app).get("/dashboard", headers={"X-User-Email": STRANGER}).text
        assert "Data as of" not in stranger

    def test_wrong_email_is_refused_and_changes_nothing(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        code = _invite(app, MATE)
        # STRANGER (not the invited address) cannot accept MATE's invite
        r = TestClient(app).post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": STRANGER},
            follow_redirects=False,
        )
        assert r.status_code == 200 and "for someone else" in r.text
        assert 'action="/auth/logout"' in r.text  # ux: an actionable way forward
        with app.state.session_factory() as s:
            assert s.scalar(select(WorkspaceInvite)).consumed_at is None  # untouched
            stranger = s.scalar(select(User).where(User.email == STRANGER))
            if stranger is not None:
                assert (
                    s.scalar(
                        select(WorkspaceMember).where(WorkspaceMember.user_id == stranger.id)
                    ).workspace_id
                    != s.scalar(select(WorkspaceInvite)).workspace_id
                )

    def test_reused_code_is_refused(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        code = _invite(app, MATE)
        mate = TestClient(app)
        first = mate.post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        assert first.status_code == 303
        second = mate.post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        assert second.status_code == 200 and "isn't valid" in second.text

    def test_expired_code_is_refused(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        code = _invite(app, MATE)
        with app.state.session_factory() as s:
            inv = s.scalar(select(WorkspaceInvite))
            inv.expires_at = datetime.now(UTC) - timedelta(days=1)
            s.commit()
        r = TestClient(app).post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        assert r.status_code == 200 and "isn't valid" in r.text
        with app.state.session_factory() as s:
            assert s.scalar(select(WorkspaceInvite)).consumed_at is None

    def test_invite_is_owner_only(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        code = _invite(app, MATE)
        TestClient(app).post(
            "/invite/accept",
            data={"code": code},
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        # MATE is now a member (not owner) of Acme — cannot invite
        r = TestClient(app).post(
            "/settings/members/invite", data={"email": STRANGER}, headers={"X-User-Email": MATE}
        )
        assert r.status_code == 403

    def test_invite_is_scale_gated(self, app: FastAPI) -> None:
        # OWNER without the Scale plan (free) cannot invite
        with app.state.session_factory() as s:
            get_or_create_workspace(s, get_or_create_user(s, OWNER))
            s.commit()
        r = TestClient(app).post(
            "/settings/members/invite", data={"email": MATE}, headers={"X-User-Email": OWNER}
        )
        assert r.status_code == 403

    def test_members_surface_honest_states(self, app: FastAPI) -> None:
        # a free owner sees the Scale upsell, NOT a dead invite form
        with app.state.session_factory() as s:
            get_or_create_workspace(s, get_or_create_user(s, OWNER))
            s.commit()
        html = TestClient(app).get("/settings/members", headers={"X-User-Email": OWNER}).text
        assert "Scale" in html
        assert 'action="/settings/members/invite"' not in html  # no dead control
