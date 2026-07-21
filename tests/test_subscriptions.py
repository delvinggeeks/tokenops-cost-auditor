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
        # R-PRICING-FINAL-2 superseded R-Q11's both-currency display: each
        # viewer sees ONE currency, and launch prices come from config too.
        assert cat["pro"].launch_usd == settings.plan_pro_usd_launch
        assert cat["pro"].launch_inr == settings.plan_pro_inr_launch
        assert cat["team"].launch_inr is None, "India Scale is flat — no launch tier"
        # Free is genuinely free — no price, no card. R-FREE-CONNECT
        # (2026-07-27) superseded R-Q5's zero: one connection, one metered audit.
        assert cat["free"].usd is None and cat["free"].sources == 1
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


@pytest.fixture()
def webhook_app(tmp_path: Path) -> FastAPI:
    """An app with TEST-MODE webhook secrets configured. The suite previously
    SKIPPED every webhook test because the shared fixture has no secret, so
    the FR-27 dedup rail was never actually exercised (V-D8 vv gate f.2)."""
    from tokenops_cost_auditor.main import create_app
    from tokenops_cost_auditor.persistence.models import Base as ModelBase

    settings = Settings(
        app_env="test",
        secret_key="w" * 64,
        database_url=f"sqlite:///{tmp_path / 'wh.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        backup_dir=tmp_path / "backups",
        stripe_webhook_secret=SECRET,
        razorpay_webhook_secret=SECRET,
        _env_file=None,
    )
    app = create_app(settings)
    ModelBase.metadata.create_all(app.state.engine)
    return app


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

    def test_01_subscription_events_are_deduplicated_like_payments(
        self, webhook_app: FastAPI
    ) -> None:
        """T-SUB-01: FR-27 rails apply to subscription events too — replay of
        the same event id must not move the subscription twice."""
        app = webhook_app
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

    def test_bad_signature_is_rejected(self, webhook_app: FastAPI) -> None:
        app = webhook_app
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

    def test_unknown_event_types_are_ignored_not_errors(self, webhook_app: FastAPI) -> None:
        resp = self._post_stripe(
            webhook_app, {"id": "evt_z", "type": "customer.updated", "data": {"object": {}}}
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
        # ONE currency per view (R-PRICING-FINAL-2 superseded R-Q11): default
        # is USD, the INR set is one toggle away, and neither view mixes.
        assert "$" in page.text and "₹499" not in page.text
        inr = client.get("/billing?ccy=INR", headers={"X-User-Email": EMAIL}).text
        assert "₹" in inr
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
        assert cat["pro"].price("INR") == settings.plan_pro_inr
        assert cat["pro"].price("INR", launch=True) == settings.plan_pro_inr_launch
        assert cat["team"].price("INR", launch=True) == settings.plan_team_inr, (
            "no launch tier means launch pricing falls back to list"
        )
        # an unknown plan key degrades to Free rather than raising
        assert plans.get(settings, "enterprise-platinum").key == "free"
        assert plans.currency_for_country(None) == "USD"
        assert plans.one_shot_display(settings, "USD") == f"${settings.one_shot_usd:,.0f}"
        # Both sides pinned: asserting only the USD half is how the INR half
        # drifted into the Terms page unnoticed (V-D10).
        assert plans.one_shot_display(settings, "INR") == f"₹{settings.one_shot_inr:,.0f}"

    def test_terms_page_quotes_the_price_we_actually_charge(self, client: TestClient) -> None:
        """A binding document must never disagree with the checkout (V-D10:
        Terms once hardcoded a price 44% under what the card was charged).
        R-PRICING-FINAL-2 made ₹20,000 THE config price (one_shot_inr) and
        Terms names BOTH markets from config — contractual completeness, not
        pricing-page mixing. The stale FX-derived figure must stay gone."""
        html = client.get("/legal/terms").text
        settings = Settings()
        assert plans.one_shot_terms_display(settings) in html
        assert "₹45,000" not in html


class TestColdReviewRegressionsV8:
    """V-D8 cold-review FAIL (2026-07-22) — f.1..f.6, money paths."""

    def test_f1_mixed_case_email_does_not_lose_a_paid_upgrade(
        self, session: Session, settings: Settings
    ) -> None:
        """A case-mismatched lookup missed, the insert hit users.email UNIQUE,
        and the provider retried forever — the upgrade never landed."""
        subscriptions.apply_event(
            session,
            settings,
            "stripe",
            SubscriptionEvent("e1", "Owner@Example.COM", "activated", "pro", "USD", "s1"),
        )
        session.commit()
        # second event, different casing again — must find the SAME user
        subscriptions.apply_event(
            session,
            settings,
            "stripe",
            SubscriptionEvent("e2", "OWNER@example.com", "renewed", "team", "USD", "s1"),
        )
        session.commit()
        users = session.execute(select(User)).scalars().all()
        assert len(users) == 1 and users[0].email == "owner@example.com"
        assert sub_of(session).plan == "team", "the upgrade must land, not deadlock"

    def test_f2_day_zero_actually_emails_the_customer(
        self, session: Session, settings: Settings
    ) -> None:
        """R-Q11/12 day 0 is 'email + provider retries'. The sweep can never
        send it — by then status already equals the stage it would move to."""
        mail = CapturingMail()
        subscriptions.apply_event(session, settings, "stripe", event("activated"))
        session.commit()
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f1"), mail=mail)
        session.commit()
        assert len(mail.sent) == 1
        assert "couldn't take this month's payment" in mail.sent[0][1]
        # and a repeat failure does not email again (the clock did not restart)
        subscriptions.apply_event(session, settings, "stripe", event("failed", eid="f2"), mail=mail)
        session.commit()
        assert len(mail.sent) == 1

    def test_f3_provider_metadata_cannot_escalate_the_plan(
        self, session: Session, settings: Settings
    ) -> None:
        """Plan names arrive as provider-echoed metadata — customer-influenced
        text. An unknown value must keep the tier we already had."""
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        for bogus in ("enterprise", "admin", "", "TEAM-unlimited"):
            subscriptions.apply_event(
                session,
                settings,
                "stripe",
                SubscriptionEvent(f"x-{bogus}", EMAIL, "renewed", bogus, "USD", "s1"),
            )
            session.commit()
            assert sub_of(session).plan == "pro", f"escalated via {bogus!r}"
        # a genuine known plan still works
        subscriptions.apply_event(session, settings, "stripe", event("renewed", "team", "ok"))
        session.commit()
        assert sub_of(session).plan == "team"

    def test_f4_a_later_failure_cannot_roll_back_a_sent_dunning_email(
        self, session: Session, settings: Settings
    ) -> None:
        """Same rule already applied to alerts: commit the rung before sending."""

        class ExplodingMail:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def alert(self, to_email: str, subject: str, body: str) -> None:
                self.sent.append(to_email)
                if len(self.sent) == 2:
                    raise RuntimeError("smtp down")

        for email in ("a@example.com", "b@example.com"):
            user = User(email=email)
            session.add(user)
            session.flush()
            session.add(
                Subscription(
                    user_id=user.id, provider="stripe", plan="pro", status=PAST_DUE, failed_at=T0
                )
            )
        session.commit()
        mail = ExplodingMail()
        with pytest.raises(RuntimeError):
            subscriptions.advance_dunning(session, settings, mail, now=T0 + timedelta(days=8))
        session.rollback()
        moved = [
            s
            for s in session.execute(select(Subscription)).scalars().all()
            if s.status == READ_ONLY
        ]
        assert len(moved) >= 1, "the first rung's state must survive its own send"

    def test_f5_entitlements_are_batched_not_per_source(
        self, session: Session, settings: Settings
    ) -> None:
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        user = session.execute(select(User)).scalars().one()
        batched = subscriptions.entitlements_for(session, settings, [user.id, "ghost-id"])
        assert batched[user.id]["scheduled_audits"] is True
        # a user with no subscription row reads as Free, explicitly
        assert batched["ghost-id"]["plan_key"] == "free"
        assert batched["ghost-id"]["scheduled_audits"] is False
        assert subscriptions.entitlements_for(session, settings, []) == {}

    def test_f6_no_dead_code_in_the_billing_route(self) -> None:
        source = Path("src/tokenops_cost_auditor/web/routes_billing.py").read_text(encoding="utf-8")
        assert "get_bind() and None" not in source


class TestStripeAdapterPaths:
    """stripe_link.py sat at 77.8% — its whole subscription-parsing branch was
    untested while razorpay's had direct tests (V-D8 vv gate f.1)."""

    def _adapter(self) -> object:
        from tokenops_cost_auditor.services.payments.stripe_link import StripeLinkAdapter

        return StripeLinkAdapter("https://pay.example/link", SECRET)

    def test_subscription_event_kinds_map_correctly(self) -> None:
        adapter = self._adapter()
        cases = {
            "customer.subscription.created": "activated",
            "invoice.payment_succeeded": "renewed",
            "invoice.payment_failed": "failed",
            "customer.subscription.deleted": "cancelled",
        }
        for stripe_type, kind in cases.items():
            body = json.dumps(
                {
                    "id": f"evt_{kind}",
                    "type": stripe_type,
                    "data": {
                        "object": {
                            "customer_email": EMAIL,
                            "currency": "usd",
                            "metadata": {"plan": "pro"},
                            "subscription": "sub_x",
                        }
                    },
                }
            ).encode()
            parsed = adapter.parse_subscription_event(body)
            assert parsed is not None and parsed.kind == kind
            assert parsed.currency == "USD" and parsed.email == EMAIL

    def test_email_from_metadata_when_customer_email_absent(self) -> None:
        body = json.dumps(
            {
                "id": "evt_m",
                "type": "customer.subscription.created",
                "data": {"object": {"metadata": {"email": "Meta@Example.com", "plan": "team"}}},
            }
        ).encode()
        parsed = self._adapter().parse_subscription_event(body)
        assert parsed is not None and parsed.email == "meta@example.com"
        assert parsed.plan == "team"

    def test_unparseable_or_emailless_events_are_ignored_never_raised(self) -> None:
        adapter = self._adapter()
        assert adapter.parse_subscription_event(b"{not json") is None
        no_email = json.dumps(
            {"id": "e", "type": "customer.subscription.created", "data": {"object": {}}}
        ).encode()
        assert adapter.parse_subscription_event(no_email) is None
        assert adapter.parse_subscription_event(json.dumps({"type": "x"}).encode()) is None

    def test_payment_link_and_signature_helpers(self) -> None:
        adapter = self._adapter()
        assert adapter.payment_link() == "https://pay.example/link"
        body = b'{"hello": 1}'
        ts = int(time.time())
        sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        assert adapter.verify_signature(body, f"t={ts},v1={sig}", now_epoch=ts) is True
        assert adapter.verify_signature(body, f"t={ts},v1=bad", now_epoch=ts) is False
        # stale timestamp fails the FR-27 tolerance
        assert adapter.verify_signature(body, f"t={ts},v1={sig}", now_epoch=ts + 10_000) is False


class TestPlanGating:
    """T-SUB-03: source counts and audit cadence per plan (named explicitly —
    the vv gate could not find this ID)."""

    def test_03_source_counts_and_cadence_follow_the_plan(
        self, session: Session, settings: Settings
    ) -> None:
        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        user = session.execute(select(User)).scalars().one()

        pro = subscriptions.entitlements(session, settings, user.id)
        assert pro["sources_allowed"] == settings.plan_source_limits["pro"] == 1
        assert pro["scheduled_audits"] is True

        subscriptions.apply_event(session, settings, "stripe", event("activated", "team", "t1"))
        session.commit()
        team = subscriptions.entitlements(session, settings, user.id)
        assert team["sources_allowed"] == settings.plan_source_limits["team"] == 5

        # Free: no connections, no scheduler (R-Q5/Q6)
        subscriptions.apply_event(session, settings, "stripe", event("cancelled", "team", "c1"))
        session.commit()
        free = subscriptions.entitlements(session, settings, user.id)
        # R-FREE-CONNECT: one source; still never scheduled
        assert free["sources_allowed"] == 1 and free["scheduled_audits"] is False

    def test_03b_scheduler_honours_the_gate(self, session: Session, settings: Settings) -> None:
        """The cadence gate is only real if the scheduler applies it."""
        from tokenops_cost_auditor.services.connectors import schedule

        subscriptions.apply_event(session, settings, "stripe", event("activated", "pro"))
        session.commit()
        user = session.execute(select(User)).scalars().one()
        session.add(
            Source(
                user_id=user.id,
                provider="openai",
                label="s",
                credentials_encrypted="x",
                last_pull_at=T0,
                last_audit_at=None,
            )
        )
        session.commit()
        now = T0 + timedelta(days=1)
        assert len(schedule.due_audits(session, now, settings)) == 1
        sub_of(session).status = READ_ONLY  # day-7 rung
        session.commit()
        assert schedule.due_audits(session, now, settings) == []
        assert len(schedule.due_audits(session, now)) == 1, "ungated call still sees it"
