"""O-2 RBAC — the permission matrix (web/authz.py). Pure, no DB: pins every cell of
the mockup's matrix so a future edit can't silently widen a role."""

import pytest
from fastapi import HTTPException

from tokenops_cost_auditor.web import authz
from tokenops_cost_auditor.web.authz import Perm

_GOVERN = (Perm.MANAGE_SOURCES, Perm.MANAGE_MEMBERS, Perm.MANAGE_BILLING, Perm.MANAGE_WORKSPACE)


class TestMatrix:
    def test_owner_has_every_permission(self) -> None:
        assert all(authz.can("owner", p) for p in Perm)

    def test_viewer_can_only_view(self) -> None:
        assert authz.can("viewer", Perm.VIEW)
        assert not authz.can("viewer", Perm.RUN_AUDITS)
        assert not any(authz.can("viewer", p) for p in _GOVERN)

    def test_member_runs_but_governs_nothing(self) -> None:
        assert authz.can("member", Perm.VIEW)
        assert authz.can("member", Perm.RUN_AUDITS)  # the locked cell: member runs audits
        assert not any(authz.can("member", p) for p in _GOVERN)

    def test_admin_governs_but_not_money_or_ownership(self) -> None:
        for p in (Perm.VIEW, Perm.RUN_AUDITS, Perm.MANAGE_SOURCES, Perm.MANAGE_MEMBERS):
            assert authz.can("admin", p)  # the locked cell: admin manages members
        assert not authz.can("admin", Perm.MANAGE_BILLING)
        assert not authz.can("admin", Perm.MANAGE_WORKSPACE)

    def test_unknown_and_none_role_fail_closed(self) -> None:
        for p in Perm:
            assert not authz.can(None, p)
            assert not authz.can("banana", p)


class TestManageMember:
    def test_manager_governs_any_non_owner(self) -> None:
        assert authz.can_manage_member("owner", "member")
        assert authz.can_manage_member("admin", "member")
        assert authz.can_manage_member("admin", "admin")

    def test_the_owner_is_never_a_target(self) -> None:
        assert not authz.can_manage_member("owner", "owner")
        assert not authz.can_manage_member("admin", "owner")  # no privilege inversion

    def test_a_non_manager_governs_nobody(self) -> None:
        assert not authz.can_manage_member("member", "viewer")
        assert not authz.can_manage_member("viewer", "member")


class TestAssignableRoles:
    def test_managers_assign_non_owner_roles_only(self) -> None:
        assert set(authz.assignable_roles("owner")) == {"admin", "member", "viewer"}
        assert set(authz.assignable_roles("admin")) == {"admin", "member", "viewer"}
        assert "owner" not in authz.assignable_roles("owner")

    def test_non_managers_assign_nothing(self) -> None:
        assert authz.assignable_roles("member") == ()
        assert authz.assignable_roles(None) == ()


class TestEnsure:
    def test_raises_403_when_denied(self) -> None:
        with pytest.raises(HTTPException) as ei:
            authz.ensure("viewer", Perm.RUN_AUDITS, detail="nope")
        assert ei.value.status_code == 403

    def test_no_raise_when_allowed(self) -> None:
        authz.ensure("member", Perm.RUN_AUDITS, detail="x")  # must not raise


class TestPermsContext:
    def test_viewer_context_is_all_false_but_view(self) -> None:
        c = authz.perms_context("viewer")
        assert c["role"] == "viewer"
        assert c["can_run"] is False
        assert c["can_manage_sources"] is False
        assert c["can_manage_members"] is False
        assert c["can_view_billing"] is False
        assert c["assignable_roles"] == ()

    def test_billing_visibility_is_owner_only(self) -> None:
        assert authz.perms_context("owner")["can_view_billing"] is True
        assert authz.perms_context("admin")["can_view_billing"] is False
