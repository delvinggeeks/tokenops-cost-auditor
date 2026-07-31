"""D9 tests — T-PAY-01..07 (webhooks, credits, FR-27) and T-ADM-01..05 (admin).

R-PAY ruling: webhook signature fixtures are computed INDEPENDENTLY of the
adapters under test — raw hmac/hashlib lines below mirror the provider formulas
(Razorpay: hex HMAC-SHA256 of the body; Stripe: hex HMAC-SHA256 of "t.body").
"""

import hashlib
import hmac
import io
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from test_runner import seed_audit
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import AuditLogEntry, Base, Payment
from tokenops_cost_auditor.services.runner import AuditRunner

FIXTURES = Path(__file__).parent / "fixtures"
F1_BYTES = (FIXTURES / "openai_small.jsonl").read_bytes()
RZP_SECRET = "rzp-webhook-secret"
STRIPE_SECRET = "stripe-webhook-secret"
ADMIN_TOKEN = "admin-token-for-tests"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def papp(tmp_path: Path) -> Iterator[FastAPI]:
    settings = Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite:///{tmp_path / 'pay.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        admin_token=ADMIN_TOKEN,
        razorpay_webhook_secret=RZP_SECRET,
        razorpay_payment_link_url="https://rzp.io/l/tokenops-audit",
        stripe_webhook_secret=STRIPE_SECRET,
        stripe_payment_link_url="https://buy.stripe.com/tokenops-audit",
        _env_file=None,  # type: ignore[call-arg]
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def pclient(papp: FastAPI) -> TestClient:
    return TestClient(papp)


def rzp_event(email: str, event_id: str, created_at: int) -> bytes:
    return json.dumps(
        {
            "event": "payment_link.paid",
            "event_id": event_id,
            "created_at": created_at,
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{event_id}",
                        "amount": 2000000,  # paise = INR 20,000
                        "currency": "INR",
                        "notes": {"email": email},
                    }
                }
            },
        }
    ).encode()


def rzp_sign(body: bytes) -> str:
    # independent fixture computation (R-PAY): provider formula, not adapter code
    return hmac.new(RZP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def stripe_event(email: str, event_id: str, created: int) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "created": created,
            "data": {
                "object": {
                    "id": f"cs_{event_id}",
                    "amount_total": 50000,  # cents = USD 500
                    "currency": "usd",
                    "customer_email": email,
                }
            },
        }
    ).encode()


def stripe_sig(body: bytes, t: int) -> str:
    v1 = hmac.new(STRIPE_SECRET.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def upload(client: TestClient, email: str):
    return client.post(
        "/api/v1/audits",
        headers={"X-User-Email": email},
        files={"file": ("logs.jsonl", io.BytesIO(F1_BYTES), "application/jsonl")},
    )


@pytest.mark.verifies_requirement("FR-18")
class TestTPAY01Webhooks:
    def test_razorpay_valid_signature_grants_credit(
        self, pclient: TestClient, papp: FastAPI
    ) -> None:
        body = rzp_event("buyer@example.com", "evt1", int(time.time()))
        resp = pclient.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": rzp_sign(body)},
        )
        assert resp.json() == {"status": "processed"}
        with papp.state.session_factory() as session:
            payment = session.scalar(select(Payment))
            assert payment is not None
            assert payment.provider == "razorpay"
            assert payment.amount == 20000.0 and payment.currency == "INR"

    def test_stripe_valid_signature_grants_credit(self, pclient: TestClient, papp: FastAPI) -> None:
        now = int(time.time())
        body = stripe_event("buyer2@example.com", "evt_s1", now)
        resp = pclient.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": stripe_sig(body, now)},
        )
        assert resp.json() == {"status": "processed"}
        with papp.state.session_factory() as session:
            payment = session.scalar(select(Payment))
            assert payment is not None
            assert payment.amount == 500.0 and payment.currency == "USD"


@pytest.mark.verifies_requirement("FR-18")
class TestTPAY02InvalidSignature:
    def test_razorpay_bad_signature_400(self, pclient: TestClient) -> None:
        body = rzp_event("x@example.com", "evt2", int(time.time()))
        resp = pclient.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": "deadbeef"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "bad_request"

    def test_stripe_bad_signature_400(self, pclient: TestClient) -> None:
        now = int(time.time())
        body = stripe_event("x@example.com", "evt_s2", now)
        resp = pclient.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": f"t={now},v1=deadbeef"},
        )
        assert resp.status_code == 400


@pytest.mark.verifies_requirement("FR-18")
class TestTPAY03WebhookUnlocksUpload:
    def test_paid_then_upload_succeeds(self, pclient: TestClient) -> None:
        body = rzp_event("buyer@example.com", "evt3", int(time.time()))
        pclient.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": rzp_sign(body)},
        )
        resp = upload(pclient, "buyer@example.com")
        assert resp.status_code == 201
        # credit consumed: second upload without another payment is refused
        assert upload(pclient, "buyer@example.com").status_code == 402


@pytest.mark.verifies_requirement("FR-18")
class TestTPAY04UnpaidBlocked:
    def test_402_with_payment_links_and_envelope(self, pclient: TestClient) -> None:
        resp = upload(pclient, "unpaid@example.com")
        assert resp.status_code == 402
        body = resp.json()
        assert body["error"]["code"] == "payment_required"  # NFR-14 envelope
        assert "rzp.io" in body["error"]["message"]
        assert "buy.stripe.com" in body["error"]["message"]


@pytest.mark.verifies_requirement("FR-18")
class TestTPAY05AdminMarkPaid:
    def test_mark_paid_unlocks_and_comp_is_zero(self, pclient: TestClient, papp: FastAPI) -> None:
        resp = pclient.post(
            "/admin/payments/mark-paid",
            headers=ADMIN,
            data={
                "email": "Comp@Example.com",
                "amount": "0",
                "currency": "USD",
                "provider": "comp",
            },
        )
        assert resp.status_code == 200
        assert upload(pclient, "comp@example.com").status_code == 201
        with papp.state.session_factory() as session:
            payment = session.scalar(select(Payment))
            assert payment is not None
            assert payment.provider == "comp" and payment.amount == 0.0
            assert payment.audit_id is not None  # consumed by the upload


@pytest.mark.verifies_requirement("FR-27")
class TestTPAY06TimestampTolerance:
    def test_stale_razorpay_event_ignored(self, pclient: TestClient, papp: FastAPI) -> None:
        body = rzp_event("late@example.com", "evt4", int(time.time()) - 600)  # 10 min old
        resp = pclient.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": rzp_sign(body)},
        )
        assert resp.json() == {"status": "ignored"}  # FR-27: > 5-min tolerance
        with papp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None

    def test_stale_stripe_signature_rejected(self, pclient: TestClient) -> None:
        t = int(time.time()) - 600
        body = stripe_event("late@example.com", "evt_s4", t)
        resp = pclient.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": stripe_sig(body, t)},
        )
        assert resp.status_code == 400  # FR-27: timestamp outside tolerance


@pytest.mark.verifies_requirement("FR-27")
class TestTPAY07Dedup:
    def test_duplicate_event_acknowledged_once(self, pclient: TestClient, papp: FastAPI) -> None:
        body = rzp_event("dup@example.com", "evt5", int(time.time()))
        headers = {"X-Razorpay-Signature": rzp_sign(body)}
        first = pclient.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
        second = pclient.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
        assert first.json() == {"status": "processed"}
        assert second.json() == {"status": "duplicate"}  # 200, not reprocessed
        with papp.state.session_factory() as session:
            payments = list(session.scalars(select(Payment)))
        assert len(payments) == 1  # exactly ONE credit


@pytest.mark.verifies_requirement("FR-19")
class TestTADM01Token:
    def test_no_or_wrong_token_is_404(self, pclient: TestClient) -> None:
        assert pclient.get("/admin").status_code == 404
        assert pclient.get("/admin", headers={"X-Admin-Token": "wrong"}).status_code == 404

    def test_unset_admin_token_disables_panel(self, client: TestClient) -> None:
        # default test settings have admin_token="" -> panel does not exist
        assert client.get("/admin", headers={"X-Admin-Token": ""}).status_code == 404


@pytest.mark.verifies_requirement("FR-19")
class TestTADM02Rerun:
    def test_rerun_idempotent(self, pclient: TestClient, papp: FastAPI) -> None:
        audit_id = seed_audit(papp, "openai_small.jsonl", email="adm@example.com")
        runner: AuditRunner = papp.state.runner
        runner.run(audit_id)
        resp = pclient.post(f"/admin/audits/{audit_id}/rerun", headers=ADMIN)
        assert resp.status_code == 200
        status = pclient.get(
            f"/api/v1/audits/{audit_id}/status", headers={"X-User-Email": "adm@example.com"}
        ).json()
        assert status["status"] == "done"  # re-ran to completion, no duplicates (FR-19)


@pytest.mark.verifies_requirement("FR-19")
class TestTADM03Purge:
    def test_manual_purge(self, pclient: TestClient, papp: FastAPI) -> None:
        audit_id = seed_audit(papp, "openai_small.jsonl", email="purge@example.com")
        papp.state.runner.run(audit_id)
        resp = pclient.post(f"/admin/audits/{audit_id}/purge", headers=ADMIN)
        assert resp.json()["status"] == "purged"
        upload_dir = Path(papp.state.settings.upload_dir) / audit_id
        assert not upload_dir.exists()  # raw upload gone (FR-21 manual path)
        with papp.state.session_factory() as session:
            actions = [
                e.action
                for e in session.scalars(
                    select(AuditLogEntry).where(AuditLogEntry.subject == audit_id)
                )
            ]
        assert "audit.purged" in actions
        # re-run after purge must refuse (no source data)
        assert pclient.post(f"/admin/audits/{audit_id}/rerun", headers=ADMIN).status_code == 400


@pytest.mark.verifies_requirement("FR-19")
class TestTADM04ListView:
    def test_admin_list_shows_audits(self, pclient: TestClient, papp: FastAPI) -> None:
        audit_id = seed_audit(papp, "openai_small.jsonl", email="list@example.com")
        page = pclient.get("/admin", headers=ADMIN)
        assert page.status_code == 200
        assert audit_id in page.text
        assert "list@example.com" in page.text


@pytest.mark.verifies_requirement("FR-19")
class TestTADM05DownloadReport:
    def test_admin_downloads_pdf_and_action_is_logged(
        self, pclient: TestClient, papp: FastAPI
    ) -> None:
        audit_id = seed_audit(papp, "openai_small.jsonl", email="dl@example.com")
        papp.state.runner.run(audit_id)
        resp = pclient.get(f"/admin/audits/{audit_id}/report", headers=ADMIN)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"
        with papp.state.session_factory() as session:
            actions = [
                e.action
                for e in session.scalars(
                    select(AuditLogEntry).where(AuditLogEntry.subject == audit_id)
                )
            ]
        assert "report.admin_downloaded" in actions  # FR-20: admin action audit-logged

    def test_unknown_audit_and_unrendered_report_404(
        self, pclient: TestClient, papp: FastAPI
    ) -> None:
        assert pclient.get("/admin/audits/nonexistent/report", headers=ADMIN).status_code == 404
        audit_id = seed_audit(papp, "openai_small.jsonl", email="dl2@example.com")
        # queued but never run -> no PDF on disk yet
        assert pclient.get(f"/admin/audits/{audit_id}/report", headers=ADMIN).status_code == 404


class TestG5ColdReviewFindings:
    """Regression pins for G5 cold-reviewer findings 1/3/5."""

    def test_atomic_claim_cannot_double_spend(self, papp: FastAPI) -> None:
        """f.1: two sessions racing for ONE credit — exactly one wins."""
        from tokenops_cost_auditor.persistence.repo import get_or_create_user
        from tokenops_cost_auditor.services.payments.base import claim_credit, grant_payment

        with papp.state.session_factory() as session:
            user = get_or_create_user(session, "race@example.com")
            grant_payment(session, user.id, "manual", 500.0, "USD")
            session.commit()
            user_id = user.id
        s1 = papp.state.session_factory()
        s2 = papp.state.session_factory()
        try:
            first = claim_credit(s1, user_id, "audit-A")
            s1.commit()
            second = claim_credit(s2, user_id, "audit-B")
            s2.commit()
            assert first is not None
            assert second is None  # the same credit can never fund two audits
        finally:
            s1.close()
            s2.close()

    def test_signature_valid_garbage_payload_ignored_not_500(self, pclient: TestClient) -> None:
        """f.3: shape-drifted but correctly signed payloads must not 500."""
        body = b'{"event": "payment_link.paid", "created_at": "not-a-number"}'
        resp = pclient.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": rzp_sign(body)},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
        t = int(time.time())
        sbody = b'{"type": "checkout.session.completed", "id": "evt_g", "data": {}}'
        resp2 = pclient.post(
            "/api/v1/webhooks/stripe",
            content=sbody,
            headers={"Stripe-Signature": stripe_sig(sbody, t)},
        )
        assert resp2.status_code == 200
        assert resp2.json() == {"status": "ignored"}

    def test_negative_mark_paid_rejected(self, pclient: TestClient) -> None:
        """f.5: a negative 'credit' must never unlock uploads."""
        resp = pclient.post(
            "/admin/payments/mark-paid",
            headers=ADMIN,
            data={
                "email": "neg@example.com",
                "amount": "-500",
                "currency": "USD",
                "provider": "manual",
            },
        )
        assert resp.status_code == 400
