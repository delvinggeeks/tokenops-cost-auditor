"""O-4 — the workspace settings home (R-ORG, ROADMAP §3 #7). One tabbed home gathering
General, Members, Developer, Sign-in and Audit log; walk every tab, the tab spine, the
sidebar consolidation, and the two new surfaces (Sign-in, Audit log)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import AuditLogEntry
from tokenops_cost_auditor.persistence.repo import get_or_create_user, get_or_create_workspace

USER = "settings-owner@example.com"
HDR = {"X-User-Email": USER}
TABS = [
    "/settings",
    "/settings/members",
    "/settings/developer",
    "/settings/sign-in",
    "/settings/audit-log",
]


class TestSettingsHome:
    def test_every_tab_renders_and_carries_the_full_tab_spine(self, app: FastAPI) -> None:
        # The whole point of O-4: one home. Every settings page renders and its tab
        # spine deep-links every other tab (server-rendered, works without JS).
        c = TestClient(app)
        for url in TABS:
            page = c.get(url, headers=HDR)
            assert page.status_code == 200, url
            for tab in TABS:
                assert f'href="{tab}"' in page.text, (url, tab)

    def test_each_page_marks_its_own_tab_active(self, app: FastAPI) -> None:
        c = TestClient(app)
        cases = {
            "/settings": "/settings",
            "/settings/members": "/settings/members",
            "/settings/developer": "/settings/developer",
            "/settings/sign-in": "/settings/sign-in",
            "/settings/audit-log": "/settings/audit-log",
        }
        for url, active_href in cases.items():
            html = c.get(url, headers=HDR).text
            assert f'href="{active_href}" aria-current="page"' in html, url

    def test_sidebar_collapses_to_one_settings_item(self, app: FastAPI) -> None:
        html = TestClient(app).get("/dashboard", headers=HDR).text
        assert 'href="/settings"' in html  # the single Settings home
        # Members and Developer are no longer their own sidebar items (now tabs).
        assert 'href="/settings/members"' not in html
        assert 'href="/settings/developer"' not in html


class TestNewSurfaces:
    def test_sign_in_shows_the_account_and_no_dead_sso_control(self, app: FastAPI) -> None:
        html = TestClient(app).get("/settings/sign-in", headers=HDR).text
        assert USER in html  # your account
        assert "magic link" in html.lower()
        # Enterprise SSO is stated as a future method, never a control that 404s.
        assert "Enterprise SSO" in html

    def test_audit_log_surfaces_this_workspaces_actions(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            user = get_or_create_user(s, USER)
            get_or_create_workspace(s, user)
            s.add(AuditLogEntry(actor=USER, action="workspace.invited", subject="mate@example.com"))
            s.commit()
        html = TestClient(app).get("/settings/audit-log", headers=HDR).text
        assert "workspace invited" in html  # action rendered plainly (dots→spaces)
        assert "mate@example.com" in html  # the subject
        assert USER in html  # the actor

    def test_audit_log_empty_state_is_honest(self, app: FastAPI) -> None:
        # A brand-new workspace with no logged actions gets an honest empty state.
        html = (
            TestClient(app)
            .get("/settings/audit-log", headers={"X-User-Email": "fresh-settings@example.com"})
            .text
        )
        assert "Nothing logged yet" in html
