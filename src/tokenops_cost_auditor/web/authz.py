"""O-2 RBAC — the role→permission matrix, at the WEB/persistence boundary (R-ORG).

Roles govern who can see and do things IN OUR PRODUCT — mint a key, connect a
source, invite a member, change billing. They NEVER touch the customer's LLM
traffic (X-01/X-02), and the audit ENGINE (services/rules, services/pricing) never
imports this module — tenancy/authorization lives here, at the edge, so the engine
stays role-blind and tenant-blind. Single-tenant is unchanged: a solo user is the
`owner` of their workspace-of-one and holds every permission.

The matrix is the single source of truth (mockup: docs/design/mockups/o2-rbac.html):
    view reports/dashboard/runs   ALL roles
    run audits (upload/run)       all but viewer
    manage sources + keys         owner, admin
    manage members (invite/role)  owner, admin  (admin never over the owner)
    billing / plan                owner only
    delete/transfer workspace     owner only
"""

from __future__ import annotations

import enum

from fastapi import HTTPException

# Owner is implicit-all; the other three are the assignable roles (never owner via
# invite — ownership moves only by an explicit transfer, out of O-2 scope).
OWNER = "owner"
ROLES: tuple[str, ...] = ("owner", "admin", "member", "viewer")
ASSIGNABLE_ROLES: tuple[str, ...] = ("admin", "member", "viewer")


class Perm(enum.StrEnum):
    VIEW = "view"  # reports / dashboard / runs — every member
    RUN_AUDITS = "run_audits"  # upload + run an audit — all but viewer
    MANAGE_SOURCES = "manage_sources"  # connect/revoke sources, mint/revoke keys & devices
    MANAGE_MEMBERS = "manage_members"  # invite / revoke / set-role (never over the owner)
    MANAGE_BILLING = "manage_billing"  # billing + plan — owner only
    MANAGE_WORKSPACE = "manage_workspace"  # delete / transfer ownership — owner only


_MATRIX: dict[str, frozenset[Perm]] = {
    "owner": frozenset(Perm),  # every permission
    "admin": frozenset({Perm.VIEW, Perm.RUN_AUDITS, Perm.MANAGE_SOURCES, Perm.MANAGE_MEMBERS}),
    "member": frozenset({Perm.VIEW, Perm.RUN_AUDITS}),
    "viewer": frozenset({Perm.VIEW}),
}


def can(role: str | None, perm: Perm) -> bool:
    """True iff a member with `role` may perform `perm`. Unknown/None role = no
    permission (fail-closed — a user with no live membership can do nothing)."""
    return perm in _MATRIX.get(role or "", frozenset())


def can_manage_member(actor_role: str | None, target_role: str | None) -> bool:
    """A manager (owner/admin) may govern any NON-owner member. The owner row is
    never a target — a workspace always keeps its owner, and an admin can never act
    on the owner (no privilege inversion)."""
    return can(actor_role, Perm.MANAGE_MEMBERS) and target_role != OWNER


def assignable_roles(actor_role: str | None) -> tuple[str, ...]:
    """Roles a manager may hand out on invite or role-change — never `owner`."""
    return ASSIGNABLE_ROLES if can(actor_role, Perm.MANAGE_MEMBERS) else ()


def ensure(role: str | None, perm: Perm, *, detail: str) -> None:
    """Route-boundary guard: raise 403 (fail-closed) unless `role` grants `perm`.
    Replaces the ad-hoc inline `workspace_role(...) == 'owner'` checks so every
    mutation is gated the same way, from one matrix."""
    if not can(role, perm):
        raise HTTPException(status_code=403, detail=detail)


def perms_context(role: str | None) -> dict[str, object]:
    """Booleans for the templates so a role never SEES a control it can't use
    (R-ORG: absent, not a disabled 403-trap). Injected into every app page via
    the shell context, plus `role` and the assignable set for the member forms."""
    return {
        "role": role,
        "can_run": can(role, Perm.RUN_AUDITS),
        "can_manage_sources": can(role, Perm.MANAGE_SOURCES),
        "can_manage_members": can(role, Perm.MANAGE_MEMBERS),
        "can_view_billing": can(role, Perm.MANAGE_BILLING),  # billing visibility = owner
        "can_manage_workspace": can(role, Perm.MANAGE_WORKSPACE),
        "assignable_roles": assignable_roles(role),
    }
