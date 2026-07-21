"""Sources connect/revoke routes (PLAN-V15 WP-1): auth gate, R-Q5/Q6 plan
limits, revoke-deletes-ciphertext."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Source, Subscription, User

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}  # dev/test shim (non-prod only, FR-17)


def _grant_plan(app: FastAPI, plan: str) -> None:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan=plan))
        session.commit()


class TestSourcesRoutes:
    def test_01_auth_required(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert client.get("/sources").status_code == 401

    def test_02_free_plan_connects_one_source_only(self, app: FastAPI) -> None:
        """R-FREE-CONNECT (2026-07-27) superseded R-Q5's zero: Free connects
        ONE source (its single audit metered by the signup credit); the
        second connection hits the honest limit."""
        client = TestClient(app)
        first = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "openai", "label": "org", "api_key": "sk-x"},
            follow_redirects=False,
        )
        assert first.status_code == 303
        second = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "anthropic", "label": "org2", "api_key": "sk-y"},
        )
        assert second.status_code == 403
        assert "free" in second.json()["detail"]

    def test_03_pro_connect_limit_and_revoke(self, app: FastAPI) -> None:
        client = TestClient(app)
        _grant_plan(app, "pro")
        ok = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "anthropic", "label": "prod org", "api_key": "sk-admin-1"},
            follow_redirects=False,
        )
        assert ok.status_code == 303
        # key never rendered back
        page = client.get("/sources", headers=HDR)
        assert page.status_code == 200
        assert "prod org" in page.text and "sk-admin-1" not in page.text
        # pro = 1 active connection (R-Q5)
        deny = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "openai", "label": "second", "api_key": "sk-2"},
        )
        assert deny.status_code == 403
        # revoke deletes ciphertext, then a new connect is allowed (swap flow)
        with app.state.session_factory() as session:
            src = session.execute(select(Source)).scalars().one()
            assert src.credentials_encrypted is not None
        rev = client.post(f"/sources/{src.id}/revoke", headers=HDR, follow_redirects=False)
        assert rev.status_code == 303
        with app.state.session_factory() as session:
            gone = session.get(Source, src.id)
            assert gone is not None
            assert gone.status == "revoked" and gone.credentials_encrypted is None
        again = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "openai", "label": "swap", "api_key": "sk-3"},
            follow_redirects=False,
        )
        assert again.status_code == 303
