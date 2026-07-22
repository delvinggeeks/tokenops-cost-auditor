"""Readiness audit — payment workflow END TO END (founder: 'test payment').

Proves OUR half of the link+webhook design: a signed Razorpay webhook →
credit granted → the credit unlocks a real audit; a subscription webhook →
plan upgraded; a forged signature and a replayed event are both refused.
Only the provider's hosted checkout (a dashboard-created payment link) is
external — everything the webhook triggers is exercised here for real.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.persistence.models import Base, Payment, Subscription, User

WEBHOOK_SECRET = "whsec-test-razorpay"
BUYER = "buyer@company.com"


STRIPE_SECRET = "whsec-test-stripe"


@pytest.fixture
def payapp(tmp_path):
    settings = Settings(
        app_env="test",
        secret_key="k" * 64,
        database_url=f"sqlite:///{tmp_path / 'pay.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        razorpay_webhook_secret=WEBHOOK_SECRET,
        stripe_webhook_secret=STRIPE_SECRET,
        _env_file=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _paid_link_event(email: str = BUYER, amount_paise: int = 49900, eid: str = "evt_1") -> bytes:
    return json.dumps(
        {
            "event": "payment_link.paid",
            "event_id": eid,
            "created_at": int(time.time()),
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_" + eid,
                        "amount": amount_paise,
                        "currency": "INR",
                        "notes": {"email": email},
                    }
                }
            },
        }
    ).encode()


def _sub_activated(email: str = BUYER, plan: str = "pro", sid: str = "sub_1") -> bytes:
    return json.dumps(
        {
            "event": "subscription.activated",
            "id": sid,
            "created_at": int(time.time()),
            "payload": {
                "subscription": {"entity": {"id": sid, "notes": {"email": email, "plan": plan}}}
            },
        }
    ).encode()


def _post(client: TestClient, body: bytes, sig: str | None = None):
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": sig if sig is not None else _sign(body)},
    )


class TestPaymentWebhookEndToEnd:
    def test_a_paid_link_grants_credit_that_unlocks_an_audit(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        # before payment: uploading is refused with 402
        HDR = {"X-User-Email": BUYER}
        before = client.post(
            "/api/v1/audits",
            headers=HDR,
            files={"file": ("u.jsonl", io.BytesIO(b'{"ts":"2026-07-01T00:00:00Z"}\n'), "x")},
        )
        assert before.status_code == 402

        # the paid webhook arrives, correctly signed
        resp = _post(client, _paid_link_event())
        assert resp.status_code == 200 and resp.json()["status"] == "processed"
        with payapp.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == BUYER)).scalar_one()
            pay = s.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            assert len(pay) == 1 and pay[0].provider == "razorpay"

        # now the SAME user can run an audit — payment → credit → audit, live
        after = client.post(
            "/api/v1/audits",
            headers=HDR,
            files={"file": ("u.jsonl", io.BytesIO(b'{"ts":"2026-07-01T00:00:00Z"}\n'), "x")},
        )
        assert after.status_code == 201, after.text

    def test_a_forged_signature_is_refused_and_grants_nothing(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        resp = _post(client, _paid_link_event(), sig="deadbeef")
        assert resp.status_code == 400
        with payapp.state.session_factory() as s:
            assert s.execute(select(Payment)).scalars().all() == []

    def test_a_replayed_event_grants_exactly_one_credit(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        body = _paid_link_event(eid="evt_dup")
        assert _post(client, body).json()["status"] == "processed"
        assert _post(client, body).json()["status"] == "duplicate"  # FR-27 dedup
        with payapp.state.session_factory() as s:
            assert len(s.execute(select(Payment)).scalars().all()) == 1

    def test_a_stale_event_outside_tolerance_is_ignored(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        stale = json.loads(_paid_link_event().decode())
        stale["created_at"] = int(time.time()) - 10_000  # far outside 300s
        body = json.dumps(stale).encode()
        resp = _post(client, body)
        assert resp.json()["status"] == "ignored"
        with payapp.state.session_factory() as s:
            assert s.execute(select(Payment)).scalars().all() == []

    def test_a_subscription_activation_upgrades_the_plan(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        resp = _post(client, _sub_activated(plan="team"))
        assert resp.status_code == 200 and resp.json()["status"] == "processed"
        with payapp.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == BUYER)).scalar_one()
            sub = s.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            ).scalar_one()
            assert sub.plan == "team" and sub.status == "active"


def _stripe_sign(body: bytes) -> str:
    t = int(time.time())
    signed = f"{t}.".encode() + body
    v1 = hmac.new(STRIPE_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def _checkout_completed(email: str = "global@company.com", cents: int = 2900) -> bytes:
    return json.dumps(
        {
            "id": "evt_stripe_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_1",
                    "customer_email": email,
                    "amount_total": cents,
                    "currency": "usd",
                }
            },
        }
    ).encode()


class TestStripePaymentEndToEnd:
    """Global (USD) checkout on the SAME link+webhook design as Razorpay."""

    def test_a_signed_checkout_grants_credit_that_unlocks_an_audit(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        HDR = {"X-User-Email": "global@company.com"}
        body = _checkout_completed()
        resp = client.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": _stripe_sign(body)},
        )
        assert resp.status_code == 200 and resp.json()["status"] == "processed"
        with payapp.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == "global@company.com")).scalar_one()
            pay = s.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            assert len(pay) == 1 and pay[0].provider == "stripe" and pay[0].currency == "USD"
        after = client.post(
            "/api/v1/audits",
            headers=HDR,
            files={"file": ("u.jsonl", io.BytesIO(b'{"ts":"2026-07-01T00:00:00Z"}\n'), "x")},
        )
        assert after.status_code == 201, after.text

    def test_a_forged_stripe_signature_grants_nothing(self, payapp: FastAPI) -> None:
        client = TestClient(payapp)
        body = _checkout_completed()
        resp = client.post(
            "/api/v1/webhooks/stripe", content=body, headers={"Stripe-Signature": "t=1,v1=bad"}
        )
        assert resp.status_code == 400
        with payapp.state.session_factory() as s:
            assert s.execute(select(Payment)).scalars().all() == []
