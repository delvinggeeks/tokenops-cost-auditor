"""Readiness audit (2026-07-22) — Wave 1: ship-blockers + integrity.

One test per fix so a regression trips here with a named cause. The Microsoft
nOAuth fix lives in test_federation.py (the vulnerable test was rewritten
there); everything else is pinned below.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.persistence.models import Base, Payment, User


class TestSecretKeyStartupGuard:
    def test_prod_refuses_a_weak_secret(self, tmp_path) -> None:
        weak = Settings(
            app_env="prod",
            secret_key="dev-secret-change-me",
            database_url=f"sqlite:///{tmp_path / 'x.db'}",
            _env_file=None,
        )
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(weak)

    def test_prod_refuses_a_short_secret(self, tmp_path) -> None:
        short = Settings(
            app_env="prod",
            secret_key="tooshort",
            database_url=f"sqlite:///{tmp_path / 'x.db'}",
            _env_file=None,
        )
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(short)

    def test_prod_accepts_a_strong_secret(self, tmp_path) -> None:
        ok = Settings(
            app_env="prod",
            secret_key="k" * 64,
            database_url=f"sqlite:///{tmp_path / 'x.db'}",
            _env_file=None,
        )
        app = create_app(ok)  # must not raise
        app.state.engine.dispose()

    def test_dev_tolerates_the_default(self, tmp_path) -> None:
        # non-prod keeps the friendly default so local runs work
        app = create_app(
            Settings(app_env="dev", database_url=f"sqlite:///{tmp_path / 'x.db'}", _env_file=None)
        )
        app.state.engine.dispose()


class TestOneCompCreditPerUser:
    def test_the_index_blocks_a_second_comp_credit(self, app) -> None:
        with app.state.session_factory() as session:
            user = User(email="dupe@example.com")
            session.add(user)
            session.flush()
            session.add(Payment(user_id=user.id, provider="comp", amount=0.0, currency="USD"))
            session.commit()
            session.add(Payment(user_id=user.id, provider="comp", amount=0.0, currency="USD"))
            with pytest.raises(IntegrityError):
                session.commit()

    def test_record_login_swallows_the_race_and_keeps_the_session_alive(self, app) -> None:
        """cold-review f.2: two concurrent first-logins hit the SAVEPOINT; the
        loser is swallowed, exactly one credit exists, and the outer
        transaction survives so the login still completes."""
        from tokenops_cost_auditor.web.routes_auth import _record_login

        with app.state.session_factory() as session:
            user = User(email="racer@example.com")
            session.add(user)
            session.flush()
            _record_login(session, user, user.email, first_login=True)
            _record_login(session, user, user.email, first_login=True)  # the "race"
            assert session.is_active
            session.commit()  # must not raise
            credits = (
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )
        assert len(credits) == 1

    def test_real_paid_rows_are_unconstrained(self, app) -> None:
        with app.state.session_factory() as session:
            user = User(email="payer@example.com")
            session.add(user)
            session.flush()
            session.add(Payment(user_id=user.id, provider="stripe", amount=29.0, currency="USD"))
            session.add(Payment(user_id=user.id, provider="stripe", amount=29.0, currency="USD"))
            session.commit()  # two real payments for one user is fine
            n = session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
        assert len(n) == 2


class TestPerPlanCheckout:
    def _app(self, tmp_path, **links):
        settings = Settings(
            app_env="test",
            secret_key="s",
            database_url=f"sqlite:///{tmp_path / 'b.db'}",
            upload_dir=tmp_path / "u",
            report_dir=tmp_path / "r",
            backup_dir=tmp_path / "b",
            _env_file=None,
            **links,
        )
        application = create_app(settings)
        Base.metadata.create_all(application.state.engine)
        return application

    def test_each_plan_links_to_its_own_checkout(self, tmp_path) -> None:
        app = self._app(
            tmp_path,
            stripe_payment_link_pro="https://pay.example/PRO",
            stripe_payment_link_team="https://pay.example/TEAM",
        )
        try:
            page = TestClient(app).get("/billing", headers={"X-User-Email": "c@example.com"}).text
            # the Pro row's button must carry the PRO link, Scale's the TEAM link —
            # never a single shared link (that was the bug: wrong tier charged)
            assert "https://pay.example/PRO" in page
            assert "https://pay.example/TEAM" in page
            assert page.count("https://pay.example/PRO") == 1
        finally:
            app.state.engine.dispose()

    def test_a_plan_without_a_link_shows_not_switched_on_not_a_wrong_link(self, tmp_path) -> None:
        app = self._app(tmp_path, stripe_payment_link_pro="https://pay.example/PRO")
        try:
            page = TestClient(app).get("/billing", headers={"X-User-Email": "c@example.com"}).text
            assert "https://pay.example/PRO" in page  # Pro configured
            assert "Checkout opens once billing is switched on." in page  # Scale not
        finally:
            app.state.engine.dispose()

    def test_checkout_link_helper_never_shares_across_plans(self, tmp_path) -> None:
        s = Settings(
            secret_key="s",
            database_url=f"sqlite:///{tmp_path / 'h.db'}",
            stripe_payment_link_pro="P",
            razorpay_payment_link_team="T",
            _env_file=None,
        )
        assert s.checkout_link("USD", "pro") == "P"
        assert s.checkout_link("USD", "team") == ""  # not configured → empty, not P
        assert s.checkout_link("INR", "team") == "T"
        assert s.checkout_link("INR", "pro") == ""


class TestSigninLinkMailFailure:
    def test_smtp_failure_is_a_clean_502_not_an_uncaught_500(self, app) -> None:
        class Boom:
            def magic_link(self, *a, **k):
                raise RuntimeError("smtp down")

            def alert(self, *a, **k):
                pass

            def report_ready(self, *a, **k):
                pass

        app.state.mail = Boom()
        resp = TestClient(app, raise_server_exceptions=False).post(
            "/auth/signin-link", data={"email": "user@example.com"}
        )
        assert resp.status_code == 502
        assert "couldn't send your link" in resp.text.lower()


class TestPublicBaseUrlFallback:
    def test_empty_app_base_url_falls_back_to_the_live_origin(self) -> None:
        s = Settings(app_base_url="", _env_file=None)
        assert s.public_base_url == "https://tokenops-cost-auditor.com"

    def test_a_set_base_url_wins(self) -> None:
        s = Settings(app_base_url="https://staging.example.com", _env_file=None)
        assert s.public_base_url == "https://staging.example.com"
