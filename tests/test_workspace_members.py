"""O-1b-3 (R-ORG) — Members page & revoke, walked as owner + member.

Pins the acceptance criteria: the Members page lists who is in the workspace
(role, joined) and the pending invites; an OWNER revokes a member and that
member's NEXT request loses access (the switchable resolver falls them back to
their personal workspace — no extra step); the mutating controls are owner-only
and ABSENT for a plain member (not merely 403'd — the reachability law for
permissions); resend rotates a pending code (the old link dies); cancel withdraws
one; and a solo owner sees the honest empty state.
"""

from __future__ import annotations

from datetime import timedelta
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
    list_workspace_members,
)
from tokenops_cost_auditor.services.mail.base import LogMailAdapter

OWNER = "members-owner@example.com"
MATE = "members-mate@example.com"
STRANGER = "members-stranger@example.com"


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
    """OWNER owns a named workspace on the Scale (team) plan, with a done audit to
    share, so a member's access is observable on the dashboard."""
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


def _grow(app: FastAPI, invitee: str) -> None:
    """Invite + accept: `invitee` becomes a real member of Acme (active there)."""
    code = _invite(app, invitee)
    r = TestClient(app).post(
        "/invite/accept",
        data={"code": code},
        headers={"X-User-Email": invitee},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.status_code


def _acme_ws(app: FastAPI) -> str:
    with app.state.session_factory() as s:
        owner = s.scalar(select(User).where(User.email == OWNER))
        ws = active_workspace_id(s, owner.id)
        assert ws is not None
        return ws


def _member_id(app: FastAPI, email: str) -> str:
    """The WorkspaceMember.id for `email` inside Acme — the revoke target."""
    ws = _acme_ws(app)
    with app.state.session_factory() as s:
        u = s.scalar(select(User).where(User.email == email))
        mid = s.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == ws, WorkspaceMember.user_id == u.id
            )
        )
        assert mid is not None
        return str(mid)


class TestMembersPageAndRevoke:
    def test_owner_sees_roster_then_revokes_member_who_loses_access(self, app: FastAPI) -> None:
        _seed_scale_owner(app)
        _grow(app, MATE)

        # (1) the roster lists both people with role + joined, and a Remove control
        # for the member (the owner row is never revocable).
        page = TestClient(app).get("/settings/members", headers={"X-User-Email": OWNER}).text
        assert OWNER in page and MATE in page
        assert "owner" in page and "Joined" in page  # role cell + roster column
        mate_mid = _member_id(app, MATE)
        assert f"/settings/members/{mate_mid}/revoke" in page

        # baseline: the member currently sees the shared workspace's audit
        before = TestClient(app).get("/dashboard", headers={"X-User-Email": MATE}).text
        assert "Data as of" in before and "Acme Corp" in before

        # (2) owner revokes → 303 back to the surface with the honest banner
        r = TestClient(app).post(
            f"/settings/members/{mate_mid}/revoke",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/settings/members?removed=1"

        # the membership row is gone AND the resolver falls the ex-member back to
        # their own personal workspace on their very next request
        with app.state.session_factory() as s:
            mate_u = s.scalar(select(User).where(User.email == MATE))
            assert (
                s.scalar(
                    select(WorkspaceMember).where(
                        WorkspaceMember.user_id == mate_u.id,
                        WorkspaceMember.workspace_id == _acme_ws(app),
                    )
                )
                is None
            )
            assert active_workspace_id(s, mate_u.id) != _acme_ws(app)  # fell back

        # access STOPS: the ex-member no longer sees the shared audit
        after = TestClient(app).get("/dashboard", headers={"X-User-Email": MATE}).text
        assert "Data as of" not in after

    def test_revoke_control_absent_for_plain_member_and_route_is_owner_only(
        self, app: FastAPI
    ) -> None:
        _seed_scale_owner(app)
        _grow(app, MATE)
        owner_mid = _member_id(app, OWNER)

        # a plain member sees the roster but NO mutating control at all — absent,
        # not a 403 they'd have to bump into (reachability law for permissions)
        page = TestClient(app).get("/settings/members", headers={"X-User-Email": MATE}).text
        assert OWNER in page and MATE in page  # roster visible to the member
        assert "/revoke" not in page
        assert 'action="/settings/members/invite"' not in page  # no invite form

        # and the route itself is owner-only: a member cannot revoke anyone
        r = TestClient(app).post(
            f"/settings/members/{owner_mid}/revoke",
            headers={"X-User-Email": MATE},
            follow_redirects=False,
        )
        assert r.status_code == 403

    def test_owner_row_cannot_be_removed(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        owner_mid = _member_id(app, OWNER)
        r = TestClient(app).post(
            f"/settings/members/{owner_mid}/revoke",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 400  # a workspace always keeps its owner

    def test_foreign_or_unknown_member_id_is_404(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        # STRANGER's own personal-workspace membership id — not a member of Acme
        with app.state.session_factory() as s:
            stranger = get_or_create_user(s, STRANGER)
            s.commit()
            foreign_mid = s.scalar(
                select(WorkspaceMember.id).where(WorkspaceMember.user_id == stranger.id)
            )
        r = TestClient(app).post(
            f"/settings/members/{foreign_mid}/revoke",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 404  # no cross-workspace reach

    def test_solo_owner_sees_honest_empty_state(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        page = TestClient(app).get("/settings/members", headers={"X-User-Email": OWNER}).text
        assert "just you so far" in page

    def test_roster_lists_the_owner_first(self, app: FastAPI) -> None:
        # The owner must lead the roster by ROLE, not by chronology. Backdate the
        # member's join to BEFORE the owner's, so a plain order_by(created_at)
        # would surface the member first — the owner can only lead if the explicit
        # owner-first key wins over time (cold O-1b-3 f.1 + re-gate finding 2: this
        # would fail if the case() key were dropped for a bare created_at sort).
        _seed_scale_owner(app, with_audit=False)
        _grow(app, MATE)
        ws = _acme_ws(app)
        with app.state.session_factory() as s:
            owner_m = s.scalar(
                select(WorkspaceMember)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(WorkspaceMember.workspace_id == ws, User.email == OWNER)
            )
            mate_m = s.scalar(
                select(WorkspaceMember)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(WorkspaceMember.workspace_id == ws, User.email == MATE)
            )
            mate_m.created_at = owner_m.created_at - timedelta(days=1)  # joined earlier
            s.commit()
        with app.state.session_factory() as s:
            rows = list_workspace_members(s, ws)
        assert [m.role for m, _ in rows] == ["owner", "member"]
        assert rows[0][1].email == OWNER


class TestPendingInviteGovernance:
    def test_resend_rotates_code_and_old_link_dies(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        old_code = _invite(app, MATE)
        with app.state.session_factory() as s:
            invite_id = s.scalar(select(WorkspaceInvite.id))

        r = TestClient(app).post(
            f"/settings/members/invite/{invite_id}/resend",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/settings/members?invited=resent"
        new_code = _code_from(app.state.mail.invites[-1][1])
        assert new_code != old_code

        # the OLD link is dead (its hash was overwritten); the NEW one is live
        old = TestClient(app).get(f"/invite/accept?code={old_code}", headers={"X-User-Email": MATE})
        assert "isn't valid" in old.text
        new = TestClient(app).get(f"/invite/accept?code={new_code}", headers={"X-User-Email": MATE})
        assert new.status_code == 200 and "Accept invitation" in new.text

    def test_resend_mail_failure_leaves_the_old_link_working(self, app: FastAPI) -> None:
        # cold O-1b-3 f.2: a resend whose email fails must NOT have already killed
        # the existing link — the invitee is left exactly as they were, not stranded.
        _seed_scale_owner(app, with_audit=False)
        old_code = _invite(app, MATE)
        with app.state.session_factory() as s:
            invite_id = s.scalar(select(WorkspaceInvite.id))

        class BoomMail(LogMailAdapter):
            def workspace_invite(self, to_email: str, link_url: str, workspace_name: str) -> None:
                raise RuntimeError("smtp down")

        app.state.mail = BoomMail()
        r = TestClient(app).post(
            f"/settings/members/invite/{invite_id}/resend",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/settings/members?invited=resend-failed"

        # the ORIGINAL link still works — the failed resend rotated nothing
        show = TestClient(app).get(
            f"/invite/accept?code={old_code}", headers={"X-User-Email": MATE}
        )
        assert show.status_code == 200 and "Accept invitation" in show.text

    def test_cancel_withdraws_pending_invite_and_kills_link(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        code = _invite(app, MATE)
        with app.state.session_factory() as s:
            invite_id = s.scalar(select(WorkspaceInvite.id))

        r = TestClient(app).post(
            f"/settings/members/invite/{invite_id}/cancel",
            headers={"X-User-Email": OWNER},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/settings/members?invited=canceled"

        # the invite row is gone; the emailed link now loads nothing → invalid
        with app.state.session_factory() as s:
            assert s.scalar(select(WorkspaceInvite)) is None
        dead = TestClient(app).get(f"/invite/accept?code={code}", headers={"X-User-Email": MATE})
        assert "isn't valid" in dead.text

    def test_resend_and_cancel_are_owner_only(self, app: FastAPI) -> None:
        _seed_scale_owner(app, with_audit=False)
        _invite(app, MATE)
        _grow(app, STRANGER)  # STRANGER is now a plain member of Acme
        with app.state.session_factory() as s:
            invite_id = s.scalar(select(WorkspaceInvite.id).where(WorkspaceInvite.email == MATE))
        for verb in ("resend", "cancel"):
            r = TestClient(app).post(
                f"/settings/members/invite/{invite_id}/{verb}",
                headers={"X-User-Email": STRANGER},
                follow_redirects=False,
            )
            assert r.status_code == 403, verb
