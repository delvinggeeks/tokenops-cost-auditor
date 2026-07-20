"""T-SUB-01..05 (PLAN-V15 V-D8 / WP-6) — subscriptions, webhooks, dunning.

This is where customer money moves, so the tests lean on the webhook paths
and the plan-transition edges: replay, out-of-order delivery, a failure
clock that must not restart, and the read-only rung touching exactly one
capability.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Base,
    Payment,
    Source,
    Subscription,
    User,
    WebhookEvent,
)
from tokenops_cost_auditor.services.payments import plans, subscriptions
from tokenops_cost_auditor.services.payments.subscriptions import (
    ACTIVE,
    CANCELLED,
    PAST_DUE,
    READ_ONLY,
    SubscriptionEvent,
)

T0 = datetime(2026, 7, 1, tzinfo=UTC)
EMAIL = "owner@example.com"
SECRET = "whsec-test"


class CapturingMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def alert(self, to_email: str, subject: str, body: str) -> None:
        self.sent.append((to_email, subject, body))


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/sub.db", _env_file=None
    )


@pytest.fixture()
def session(settings: Settings) -> Session:
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def event(kind: str, plan: str = "pro", eid: str = "evt-1") -> SubscriptionEvent:
    return SubscriptionEvent(
        event_id=eid, email=EMAIL, kind=kind, plan=plan, currency="USD", ref="sub-1"
    )


def sub_of(session: Session) -> Subscription:
    return session.execute(select(Subscription)).scalars().one()


class TestPriceConfig:
    def test_every_amount_comes_from_config_never_inline(self, settings: Settings) -> None:
        """Founder: 'every money amount rendered from one price config'."""
        cat = plans.catalogue(settings)
        assert cat["pro"].usd == settings.plan_pro_usd
        assert cat["pro"].inr == settings.plan_pro_inr
        assert cat["team"].usd == settings.plan_team_usd
        # both currencies are shown wherever a paid plan is (R-Q11)
        both = cat["pro"].display_both()
        assert "$" in both and "₹" in both
        # Free is genuinely free — no price, no card
        assert cat["free"].usd is None and cat["free"].sources == 0
        assert cat["free"].scheduled_audits is False

    def test_currency_routing_follows_billing_country(self) -> None:
        assert plans.currency_for_country("IN") == "INR"
        assert plans.provider_for_currency("INR") == "razorpay"
        assert plans.currency_for_country("GB") == "USD"
        assert plans.provider_for_currency("USD") == "stripe"

    def test_no_price_is_hard_coded_in_templates_or_routes(self) -> None:
        """A literal 99/299 in a template would drift the day a price changes."""
        for path in [
            *Path("src/tokenops_cost_auditor/web/templates/app").rglob("*.html"),
            Path("src/tokenops_cost_auditor/web/routes_billing.py"),
        ]:
            text = path.read_text(encoding="utf-8")
            for literal in ("$99", "$299", "8,999", "26,999", "₹8999"):
                assert literal not in text, f"inline price {literal} in {path}"


class TestPlanTransitions:
    def test_02_activate_renew_fail_cancel(self, session: Session, settings: Settings) -> None:
        """T-SUB-02: the whole lifecycle, in order."""
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        assert (sub_of(session).plan, sub_of(session).status) == ("pro", ACTIVE)

        subscriptions.apply_event(session, settings, "stripe", event("renewed", "team", "evt-2"))
        session.commit()
        assert (sub_of(session).plan, sub_of(session).status) == ("team", ACTIVE)

        subscriptions.apply_event(session, settings, "stripe", event("failed", "team", "evt-3"))
        session.commit()
        assert sub_of(session).status == PAST_DUE
        assert sub_of(session).failed_at is not None
        assert sub_of(session).plan == "team", "a failed charge does not downgrade the plan"

        subscriptions.apply_event(session, settings, "stripe", event("cancelled", "team", "evt-4"))
        session.commit()
        assert (sub_of(session).plan, sub_of(session).status) == ("free", CANCELLED)

    def test_a_repeated_failure_does_not_restart_the_clock(
        self, session: Session, settings: Settings
    ) -> None:
        """Otherwise the ladder never reaches day 7 — a customer could fail
        payment forever and keep a paid plan."""
        subscriptions.apply_event(session, settings, "stripe", event("activated"))
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f1"))
        session.commit()
        first = sub_of(session).failed_at
        assert first is not None
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f2"))
        session.commit()
        assert sub_of(session).failed_at == first

    def test_a_successful_charge_clears_the_dunning_clock(
        self, session: Session, settings: Settings
    ) -> None:
        subscriptions.apply_event(session, settings, "stripe", event("activated"))
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f1"))
        session.commit()
        assert sub_of(session).failed_at is not None
        subscriptions.apply_event(session, settings, "stripe", event("renewed", eid="r1"))
        session.commit()
        assert sub_of(session).failed_at is None and sub_of(session).status == ACTIVE

    def test_downgrade_keeps_sources_but_entitlement_shrinks(
        self, session: Session, settings: Settings
    ) -> None:
        """R-Q6: extra sources are paused, never deleted. The entitlement
        number is what changes."""
        subscriptions.apply_event(session, settings, "stripe", event("activated", "team"))
        session.commit()
        user = session.execute(select(User)).scalars().one()
        for i in range(3):
            session.add(
                Source(user_id=user.id, provider="openai", label=f"s{i}", credentials_encrypted="x")
            )
        session.commit()
        assert subscriptions.entitlements(session, settings, user.id)["sources_allowed"] == 5
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro", "e9"))
        session.commit()
        ent = subscriptions.entitlements(session, settings, user.id)
        assert ent["sources_allowed"] == 1
        assert len(session.execute(select(Source)).scalars().all()) == 3, "sources not deleted"


class TestDunningLadder:
    @pytest.mark.parametrize(
        ("days", "expected"),
        [(0, PAST_DUE), (6, PAST_DUE), (7, READ_ONLY), (20, READ_ONLY), (21, CANCELLED)],
    )
    def test_04_rungs_are_exactly_where_the_ruling_says(
        self, settings: Settings, days: int, expected: str
    ) -> None:
        """T-SUB-04: day 0 past_due, day 7 read-only, day 21 cancelled."""
        assert subscriptions.dunning_stage(T0, T0 + timedelta(days=days), settings) == expected

    def test_sweep_is_idempotent_and_emails_once_per_rung(
        self, session: Session, settings: Settings
    ) -> None:
        subscriptions.apply_event(session, settings, "stripe", event("activated"))
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f1"))
        session.commit()
        sub_of(session).failed_at = T0
        session.commit()
        mail = CapturingMail()
        day8 = T0 + timedelta(days=8)
        assert subscriptions.advance_dunning(session, settings, mail, now=day8)["read_only"] == 1
        assert sub_of(session).status == READ_ONLY
        assert len(mail.sent) == 1
        # a second sweep on the same day changes nothing and sends nothing
        assert subscriptions.advance_dunning(session, settings, mail, now=day8) == {
            "past_due": 0,
            "read_only": 0,
            "cancelled": 0,
        }
        assert len(mail.sent) == 1

    def test_cancellation_reverts_to_free_and_deletes_nothing(
        self, session: Session, settings: Settings
    ) -> None:
        subscriptions.apply_event(session, settings, "stripe", event("activated", "team"))
        session.commit()
        user = session.execute(select(User)).scalars().one()
        session.add(
            Source(user_id=user.id, provider="openai", label="keep me", credentials_encrypted="x")
        )
        sub_of(session).failed_at = T0
        session.commit()
        mail = CapturingMail()
        subscriptions.advance_dunning(session, settings, mail, now=T0 + timedelta(days=25))
        assert (sub_of(session).status, sub_of(session).plan) == (CANCELLED, "free")
        assert len(session.execute(select(Source)).scalars().all()) == 1
        body = mail.sent[-1][2]
        assert "Nothing has been deleted" in body

    def test_read_only_pauses_scheduled_audits_and_nothing_else(
        self, session: Session, settings: Settings
    ) -> None:
        """R-Q12: dashboard visible, connections kept, only the schedule stops."""
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        user = session.execute(select(User)).scalars().one()
        sub_of(session).status = READ_ONLY
        session.commit()
        ent = subscriptions.entitlements(session, settings, user.id)
        assert ent["scheduled_audits"] is False
        assert ent["dashboard_visible"] is True
        assert ent["connections_kept"] is True
        assert ent["read_only"] is True


class TestWebhookRails:
    def _post_stripe(self, app: FastAPI, payload: dict) -> object:
        body = json.dumps(payload).encode()
        ts = int(time.time())
        secret = app.state.settings.stripe_webhook_secret
        signed = f"{ts}.".encode() + body
        sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return TestClient(app).post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": f"t={ts},v1={sig}", "content-type": "application/json"},
        )

    def test_01_subscription_events_are_deduplicated_like_payments(self, app: FastAPI) -> None:
        """T-SUB-01: FR-27 rails apply to subscription events too — replay of
        the same event id must not move the subscription twice."""
        if not app.state.settings.stripe_webhook_secret:
            pytest.skip("stripe webhook secret not configured in this fixture")
        payload = {
            "id": "evt_sub_1",
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "customer_email": EMAIL,
                    "currency": "usd",
                    "metadata": {"plan": "pro"},
                    "subscription": "sub_1",
                }
            },
        }
        first = self._post_stripe(app, payload)
        assert first.status_code == 200 and first.json()["status"] == "processed"
        replay = self._post_stripe(app, payload)
        assert replay.json()["status"] == "duplicate"
        with app.state.session_factory() as session:
            events = session.execute(select(WebhookEvent)).scalars().all()
            assert len([e for e in events if e.event_id == "evt_sub_1"]) == 1
            subs = session.execute(select(Subscription)).scalars().all()
            assert len(subs) == 1 and subs[0].plan == "pro"

    def test_bad_signature_is_rejected(self, app: FastAPI) -> None:
        if not app.state.settings.stripe_webhook_secret:
            pytest.skip("stripe webhook secret not configured in this fixture")
        body = json.dumps(
            {
                "id": "evt_x",
                "type": "customer.subscription.created",
                "data": {"object": {"customer_email": EMAIL}},
            }
        ).encode()
        resp = TestClient(app).post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        assert resp.status_code == 400

    def test_unknown_event_types_are_ignored_not_errors(self, app: FastAPI) -> None:
        if not app.state.settings.stripe_webhook_secret:
            pytest.skip("stripe webhook secret not configured in this fixture")
        resp = self._post_stripe(
            app, {"id": "evt_z", "type": "customer.updated", "data": {"object": {}}}
        )
        assert resp.status_code == 200 and resp.json()["status"] == "ignored"

    def test_razorpay_subscription_parsing_and_staleness(self) -> None:
        from tokenops_cost_auditor.services.payments.razorpay_link import RazorpayLinkAdapter

        adapter = RazorpayLinkAdapter("", SECRET)
        now = int(time.time())
        body = json.dumps(
            {
                "id": "evt_rz_1",
                "event": "subscription.charged",
                "created_at": now,
                "payload": {
                    "subscription": {
                        "entity": {"id": "sub_rz", "notes": {"email": EMAIL, "plan": "team"}}
                    }
                },
            }
        ).encode()
        parsed = adapter.parse_subscription_event(body, now_epoch=now)
        assert parsed is not None
        assert (parsed.kind, parsed.plan, parsed.currency) == ("renewed", "team", "INR")
        # FR-27 timestamp tolerance applies to subscription events as well
        stale = adapter.parse_subscription_event(body, now_epoch=now + 10_000)
        assert stale is None
        # a malformed payload is ignored, never a 500
        assert adapter.parse_subscription_event(b"{not json", now_epoch=now) is None


class TestOneShotUnchanged:
    def test_05_one_shot_credit_path_still_works(self, session: Session) -> None:
        """T-SUB-05: subscriptions must not disturb the $500 one-shot flow."""
        from tokenops_cost_auditor.services.payments.base import (
            grant_payment,
            unconsumed_credit,
        )

        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        grant_payment(session, user.id, "manual", 500.0, "USD")
        session.commit()
        credit = unconsumed_credit(session, user.id)
        assert credit is not None and credit.amount == 500.0
        assert session.execute(select(Payment)).scalars().all() != []


class TestBillingPage:
    def test_page_shows_plan_prices_and_state_in_words(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert client.get("/billing").status_code == 401
        page = client.get("/billing", headers={"X-User-Email": EMAIL})
        assert page.status_code == 200
        # both currencies for paid plans (R-Q11), no card ask for Free
        assert "$" in page.text and "₹" in page.text
        assert "No card required" in page.text
        assert "One-off audit" in page.text
        assert "never reach our servers" in page.text

    def test_read_only_state_is_explained_not_just_flagged(self, app: FastAPI) -> None:
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            session.add(
                Subscription(user_id=user.id, provider="stripe", plan="pro", status=READ_ONLY)
            )
            session.commit()
        page = TestClient(app).get("/billing", headers={"X-User-Email": EMAIL}).text
        assert "Scheduled audits are paused" in page
        assert "connections are untouched" in page or "connections are all still here" in page

    def test_cancelled_account_reads_as_free_with_nothing_deleted(self, app: FastAPI) -> None:
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            session.add(
                Subscription(user_id=user.id, provider="stripe", plan="free", status=CANCELLED)
            )
            session.commit()
        page = TestClient(app).get("/billing", headers={"X-User-Email": EMAIL}).text
        assert "Nothing was deleted" in page
        assert "Your plan: Free" in page


class TestPlanHelpers:
    def test_display_helpers_cover_both_currencies_and_unknown_plans(
        self, settings: Settings
    ) -> None:
        cat = plans.catalogue(settings)
        assert cat["pro"].display("INR").startswith("₹")
        assert cat["pro"].display("USD").startswith("$")
        assert cat["free"].display("USD") == "—"
        assert cat["free"].display_both() == "—"
        assert cat["pro"].price("INR") == settings.plan_pro_inr
        # an unknown plan key degrades to Free rather than raising
        assert plans.get(settings, "enterprise-platinum").key == "free"
        assert plans.currency_for_country(None) == "USD"
        assert "$500" in plans.one_shot_display(settings)
