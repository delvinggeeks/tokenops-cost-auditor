"""Workspace members & invites (O-1b-2, R-ORG). Grow a workspace: an OWNER on
the Scale plan invites a teammate by email; the teammate accepts by signing in
with that email and is dropped INTO the shared workspace (reusing O-1b-1's
active-workspace switch spine).

Security grammar (mirrors the device link-code in routes_devices):
- the invite code is a SECRET shown once, stored only as a keyed HMAC (code_hash);
- acceptance requires the logged-in user's email to MATCH the invite email — a
  leaked code alone cannot join a different account (defense in depth);
- acceptance is single-use via an atomic UPDATE-where-unconsumed, rowcount-checked,
  so two concurrent accepts cannot both add a membership;
- minting is OWNER-ONLY, Scale-gated (the plan sold as multi-seat), rate-limited.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from tokenops_cost_auditor.api.routes_upload import EMAIL_RE, current_user
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import (
    User,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)
from tokenops_cost_auditor.persistence.repo import (
    active_workspace_id,
    get_or_create_user,
    list_workspace_invites,
    list_workspace_members,
    set_active_workspace,
    workspace_role,
)
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.auth import resolve_session
from tokenops_cost_auditor.web.routes_dashboard import _render, _session, _shell_ctx
from tokenops_cost_auditor.web.routes_sources import user_plan

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

router = APIRouter(tags=["members"])

INVITE_TTL_DAYS = 7


def _aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes for DateTime(timezone=True); make any
    stored timestamp UTC-aware before comparing, so expiry checks never raise."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _viewer_email(request: Request) -> str | None:
    """Soft auth for the invite-accept flow: the session email, or the non-prod
    dev/test shim, or None. Returning None (instead of raising 401 like
    current_user) lets an unauthenticated invitee get an honest 'sign in to
    accept' page rather than a raw error."""
    settings = request.app.state.settings
    email = resolve_session(request, settings.secret_key, settings.session_ttl_days)
    if email:
        return email
    shim = request.headers.get("X-User-Email")
    if settings.app_env != "prod" and shim and EMAIL_RE.match(shim):
        return shim.lower()
    return None


@router.get("/settings/members", response_class=HTMLResponse)
def members_page(request: Request, user_email: str = Depends(current_user)) -> HTMLResponse:
    """The members surface (O-1b-3 + O-2 RBAC): the roster of who is in the workspace,
    the invite form (with role), the pending-invites list, and per-member governance
    (set-role + remove). The roster is visible to EVERY member (you should know who you
    share a workspace with); the mutating controls render ONLY for a MANAGER (owner or
    admin, Scale-gated) over a non-owner member. A member/viewer sees the list with NO
    governance control at all (absent, not a 403 they'd have to bump into — R-ORG: a
    role never sees a control it can't use)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        session.commit()
        ws = active_workspace_id(session, user.id)
        assert ws is not None  # ensure-created; never None for an authenticated user
        workspace = session.get(Workspace, ws)
        role = workspace_role(session, user.id, ws)
        is_owner = role == "owner"
        is_scale = user_plan(session, user.id) == "team"
        # O-2: governance (invite/revoke/set-role) belongs to any MANAGER (owner or
        # admin), never a member/viewer. Managing is Scale-gated exactly as inviting
        # always was (the plan sold as multi-seat).
        can_manage = authz.can(role, authz.Perm.MANAGE_MEMBERS)
        now = datetime.now(UTC)
        members = [
            {
                "id": m.id,
                "email": u.email,
                "role": m.role,
                "joined": m.created_at,
                "is_you": u.id == user.id,
                # A manager governs any NON-owner member — but never their own row
                # (no self-revoke / self-demote) and never the owner (can_manage_member).
                "can_govern": authz.can_manage_member(role, m.role) and u.id != user.id,
            }
            for m, u in list_workspace_members(session, ws)
        ]
        invites = [
            {
                "id": inv.id,
                "email": inv.email,
                "created": inv.created_at,
                "expired": _aware(inv.expires_at) < now,
            }
            for inv in (list_workspace_invites(session, ws) if can_manage else [])
        ]
        ctx = _shell_ctx(session, request, user, "members")
        return _render(
            request,
            "app/members.html",
            workspace_name=workspace.name if workspace else "your workspace",
            is_owner=is_owner,
            is_scale=is_scale,
            can_invite=can_manage and is_scale,
            members=members,
            invites=invites,
            invite_ttl_days=INVITE_TTL_DAYS,
            invited=request.query_params.get("invited"),
            removed=request.query_params.get("removed"),
            role_updated=request.query_params.get("role"),
            **ctx,
        )


@router.post("/settings/members/invite", response_model=None)
@limiter.limit("5/minute")
def invite_member(
    request: Request,
    email: str = Form(""),
    invite_role: str = Form("member"),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """MANAGER-ONLY (owner or admin), Scale-gated, rate-limited. Mints a one-shot
    code stored only as an HMAC and emails the accept link; the raw code is never
    persisted. The invitee joins with the role the manager picked — never `owner`."""
    invitee = email.strip().lower()
    settings = request.app.state.settings
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        ws = active_workspace_id(session, user.id)
        assert ws is not None  # ensure-created; never None for an authenticated user
        # fail-closed order: prove the manager permission, THEN the plan entitlement
        role = workspace_role(session, user.id, ws)
        authz.ensure(role, authz.Perm.MANAGE_MEMBERS, detail="only an owner or admin can invite")
        if user_plan(session, user.id) != "team":
            raise HTTPException(
                status_code=403, detail="inviting teammates is part of Scale — see /billing"
            )
        if not EMAIL_RE.match(invitee):
            return RedirectResponse("/settings/members?invited=-1", status_code=303)
        # the assigned role must be one a manager may hand out (never owner); an
        # unknown/forged value falls back to least-privilege 'member', never higher.
        assigned = invite_role if invite_role in authz.assignable_roles(role) else "member"
        workspace = session.get(Workspace, ws)
        code = secrets.token_urlsafe(24)
        session.add(
            WorkspaceInvite(
                workspace_id=ws,
                email=invitee,
                role=assigned,
                code_hash=credential_fingerprint(settings.secret_key, code),
                invited_by_user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
            )
        )
        auditlog.append(session, user.email, "workspace.invited", invitee)
        session.commit()
        ws_name = workspace.name if workspace else "the workspace"
    # the invite row is committed; a mail failure must not 500 the owner — the
    # log adapter shows the link in dev, and the honest banner says to retry.
    try:
        request.app.state.mail.workspace_invite(invitee, f"/invite/accept?code={code}", ws_name)
    except Exception:
        return RedirectResponse("/settings/members?invited=0", status_code=303)
    return RedirectResponse("/settings/members?invited=1", status_code=303)


@router.post("/settings/members/{member_id}/revoke", response_model=None)
def revoke_member(
    request: Request,
    member_id: str,
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """OWNER-ONLY: remove a member from the workspace. Deleting the
    `WorkspaceMember` is the whole mechanism — the switchable resolver already
    falls a revoked member back to their PERSONAL workspace on their very next
    request (`active_workspace_id` validates the active pointer against live
    membership), so access stops with no extra step; the journey test pins it.
    Guards, fail-closed: the caller must own THIS workspace; the target must be a
    member OF this workspace (a foreign/guessed id 404s, never leaks); and the
    OWNER row is never revocable (a workspace always keeps its owner — that also
    blocks an owner revoking themselves into an ownerless workspace)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        ws = active_workspace_id(session, user.id)
        assert ws is not None  # ensure-created; never None for an authenticated user
        # fail-closed base check first — a member/viewer is refused before any lookup.
        role = workspace_role(session, user.id, ws)
        authz.ensure(role, authz.Perm.MANAGE_MEMBERS, detail="you can't remove members")
        member = session.get(WorkspaceMember, member_id)
        if member is None or member.workspace_id != ws:
            raise HTTPException(status_code=404, detail="no such member in this workspace")
        # never the owner (can_manage_member encodes that — the matrix is the single
        # source of truth), never yourself (no self-revoke).
        if member.user_id == user.id or not authz.can_manage_member(role, member.role):
            raise HTTPException(status_code=400, detail="that member cannot be removed")
        removed = session.get(User, member.user_id)
        target = removed.email if removed else member.user_id
        session.delete(member)
        auditlog.append(session, user.email, "workspace.member_revoked", target)
        session.commit()
    return RedirectResponse("/settings/members?removed=1", status_code=303)


@router.post("/settings/members/{member_id}/role", response_model=None)
def set_member_role(
    request: Request,
    member_id: str,
    new_role: str = Form(""),
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """MANAGER-ONLY: change a member's role. Fail-closed: the actor must manage
    members; the target must be a NON-owner member of THIS workspace and not the
    actor themselves; the new role must be one a manager may assign (never owner —
    ownership moves only by an explicit transfer, out of O-2 scope)."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        ws = active_workspace_id(session, user.id)
        assert ws is not None
        role = workspace_role(session, user.id, ws)
        authz.ensure(role, authz.Perm.MANAGE_MEMBERS, detail="you can't change roles")
        member = session.get(WorkspaceMember, member_id)
        if member is None or member.workspace_id != ws:
            raise HTTPException(status_code=404, detail="no such member in this workspace")
        # never the owner (via can_manage_member — single source), never yourself.
        if member.user_id == user.id or not authz.can_manage_member(role, member.role):
            raise HTTPException(status_code=400, detail="that member's role cannot be changed")
        if new_role not in authz.assignable_roles(role):
            raise HTTPException(status_code=400, detail="not a role you can assign")
        member.role = new_role
        target = session.get(User, member.user_id)
        auditlog.append(
            session,
            user.email,
            "workspace.member_role_set",
            f"{target.email if target else member.user_id}:{new_role}",
        )
        session.commit()
    return RedirectResponse("/settings/members?role=1", status_code=303)


@router.post("/settings/members/invite/{invite_id}/resend", response_model=None)
@limiter.limit("5/minute")
def resend_invite(
    request: Request,
    invite_id: str,
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """OWNER-ONLY, Scale-gated, rate-limited (same email-amplification bound as a
    fresh invite): re-mint a pending invite's one-shot code and re-send the link.
    Re-minting OVERWRITES the stored hash, so the previous code is invalidated the
    instant a new one is issued — a resend is a rotation, never a second live
    code. Only an unconsumed invite of THIS workspace can be resent."""
    settings = request.app.state.settings
    # Phase 1 — authorize and read the invite. NO write, and (like invite_member)
    # the mail send is kept OUT of the DB session: hold no connection across the
    # network call (cold O-1b-3 f.2 re-gate note).
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        ws = active_workspace_id(session, user.id)
        assert ws is not None
        role = workspace_role(session, user.id, ws)
        authz.ensure(role, authz.Perm.MANAGE_MEMBERS, detail="only an owner or admin can invite")
        if user_plan(session, user.id) != "team":
            raise HTTPException(
                status_code=403, detail="inviting teammates is part of Scale — see /billing"
            )
        invite = session.get(WorkspaceInvite, invite_id)
        if invite is None or invite.workspace_id != ws or invite.consumed_at is not None:
            raise HTTPException(status_code=404, detail="no such pending invitation")
        workspace = session.get(Workspace, ws)
        invitee = invite.email
        ws_name = workspace.name if workspace else "the workspace"
        actor = user.email
    # Phase 2 — send the new link with the session closed. Rotate ONLY on success,
    # so a failed resend leaves the EXISTING (working) link intact rather than kill
    # it and strand the invitee with no way in (cold O-1b-3 f.2).
    code = secrets.token_urlsafe(24)
    try:
        request.app.state.mail.workspace_invite(invitee, f"/invite/accept?code={code}", ws_name)
    except Exception:
        return RedirectResponse("/settings/members?invited=resend-failed", status_code=303)
    # Phase 3 — commit the rotation, re-checking the invite is still a pending one
    # of this workspace (it could have been accepted or canceled during the send;
    # skip silently in that case — the mail already went, and the stale link the
    # accept/cancel produced is honestly invalid regardless).
    with _session(request) as session:
        invite = session.get(WorkspaceInvite, invite_id)
        if invite is not None and invite.workspace_id == ws and invite.consumed_at is None:
            invite.code_hash = credential_fingerprint(settings.secret_key, code)
            invite.expires_at = datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS)
            auditlog.append(session, actor, "workspace.invite_resent", invitee)
            session.commit()
    return RedirectResponse("/settings/members?invited=resent", status_code=303)


@router.post("/settings/members/invite/{invite_id}/cancel", response_model=None)
def cancel_invite(
    request: Request,
    invite_id: str,
    user_email: str = Depends(current_user),
) -> RedirectResponse:
    """OWNER-ONLY: withdraw a pending invitation. Deleting the row is the honest
    cancel — the emailed link then loads nothing and shows the same 'invalid'
    state as any dead code, so a withdrawn invite can never be accepted. No Scale
    gate: cleaning up is always allowed, even for an owner who has since lapsed."""
    with _session(request) as session:
        user = get_or_create_user(session, user_email)
        ws = active_workspace_id(session, user.id)
        assert ws is not None
        role = workspace_role(session, user.id, ws)
        authz.ensure(
            role, authz.Perm.MANAGE_MEMBERS, detail="only an owner or admin can manage invites"
        )
        invite = session.get(WorkspaceInvite, invite_id)
        if invite is None or invite.workspace_id != ws or invite.consumed_at is not None:
            raise HTTPException(status_code=404, detail="no such pending invitation")
        canceled = invite.email
        session.delete(invite)
        auditlog.append(session, user.email, "workspace.invite_canceled", canceled)
        session.commit()
    return RedirectResponse("/settings/members?invited=canceled", status_code=303)


def _load_invite(request: Request, code: str) -> WorkspaceInvite | None:
    settings = request.app.state.settings
    with _session(request) as session:
        return session.execute(
            select(WorkspaceInvite).where(
                WorkspaceInvite.code_hash == credential_fingerprint(settings.secret_key, code)
            )
        ).scalar_one_or_none()


def _accept_state(invite: WorkspaceInvite | None, viewer: str | None) -> str:
    """The honest UI state for the accept page — no oracle beyond validity."""
    if invite is None or invite.consumed_at is not None:
        return "invalid"
    if _aware(invite.expires_at) < datetime.now(UTC):
        return "invalid"
    if viewer is None:
        return "sign_in"
    if viewer.strip().lower() != invite.email.strip().lower():
        return "wrong_email"
    return "ready"


@router.get("/invite/accept", response_class=HTMLResponse)
def accept_show(request: Request, code: str = "") -> HTMLResponse:
    """Confirm page — GET NEVER consumes (mail scanners pre-fetch links; same
    reason magic-link uses a confirm step). Shows the honest state: invalid /
    sign-in-required / wrong-email / ready-to-accept."""
    invite = _load_invite(request, code)
    viewer = _viewer_email(request)
    state = _accept_state(invite, viewer)
    workspace_name = ""
    if invite is not None and state in ("ready", "sign_in", "wrong_email"):
        with _session(request) as session:
            ws = session.get(Workspace, invite.workspace_id)
            workspace_name = ws.name if ws else ""
    return _render(
        request,
        "invite_accept.html",
        state=state,
        code=code,
        invited_email=invite.email if invite else "",
        workspace_name=workspace_name,
        viewer=viewer,
    )


@router.post("/invite/accept", response_model=None)
def accept(request: Request, code: str = Form("")) -> HTMLResponse | RedirectResponse:
    """Consume the invite: single-use, email-matched, atomic. On success the
    user is a member and their active workspace is the shared one (auto-switch),
    landing on the dashboard — now scoped to that workspace."""
    viewer = _viewer_email(request)
    settings = request.app.state.settings
    now = datetime.now(UTC)
    with _session(request) as session:
        invite = session.execute(
            select(WorkspaceInvite).where(
                WorkspaceInvite.code_hash == credential_fingerprint(settings.secret_key, code)
            )
        ).scalar_one_or_none()
        state = _accept_state(invite, viewer)
        if state != "ready" or invite is None or viewer is None:
            ws = session.get(Workspace, invite.workspace_id) if invite else None
            return _render(
                request,
                "invite_accept.html",
                state=state,
                code=code,
                invited_email=invite.email if invite else "",
                workspace_name=ws.name if ws else "",
                viewer=viewer,
            )
        user = get_or_create_user(session, viewer)
        # atomic one-shot claim — two concurrent accepts cannot both take it
        claimed = session.execute(
            update(WorkspaceInvite)
            .where(WorkspaceInvite.id == invite.id, WorkspaceInvite.consumed_at.is_(None))
            .values(consumed_at=now, consumed_by_user_id=user.id)
        )
        if cast("CursorResult[Any]", claimed).rowcount != 1:
            return _render(
                request,
                "invite_accept.html",
                state="invalid",
                code=code,
                invited_email="",
                workspace_name="",
                viewer=viewer,
            )
        # add the membership (idempotent if somehow already a member) + auto-switch
        if workspace_role(session, user.id, invite.workspace_id) is None:
            session.add(
                WorkspaceMember(workspace_id=invite.workspace_id, user_id=user.id, role=invite.role)
            )
        set_active_workspace(session, user.id, invite.workspace_id)
        auditlog.append(session, user.email, "workspace.invite_accepted", invite.workspace_id)
        # expiry was enforced in _accept_state (Python, tz-safe via _aware) an
        # instant ago — the codebase keeps expiry checks in Python, not SQL, to
        # dodge SQLite naive/aware comparison bugs (see routes_devices).
        try:
            session.commit()
        except IntegrityError:
            # cold-review O-1b-2 f.2: a concurrent accept of a SECOND invite for
            # the same email already added this membership (uq_workspace_member);
            # the user is in either way. Roll back rather than 500 — reopening
            # the link switches cleanly (they're now a member, so the add skips).
            session.rollback()
    return RedirectResponse("/dashboard", status_code=303)
