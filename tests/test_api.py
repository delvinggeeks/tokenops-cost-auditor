"""D6 API tests — T-API-01..07, T-NFR-03, T-NFR-12 (docs/05 §3 + R-API amendments)."""

import io
import typing
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.obs.ratelimit import limiter, user_or_ip_key
from tokenops_cost_auditor.persistence.models import Audit, AuditLogEntry, User
from tokenops_cost_auditor.persistence.repo import queue_position
from tokenops_cost_auditor.services.runner import AuditRunner

FIXTURES = Path(__file__).parent / "fixtures"
F1_BYTES = (FIXTURES / "openai_small.jsonl").read_bytes()
ALICE = {"X-User-Email": "alice@example.com"}
BOB = {"X-User-Email": "bob@example.com"}


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def upload(client: TestClient, headers: dict, key: str | None = None, data: bytes = F1_BYTES):
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    return client.post(
        "/api/v1/audits",
        headers=h,
        files={"file": ("logs.jsonl", io.BytesIO(data), "application/jsonl")},
    )


class TestTAPI01UploadHappyPath:
    def test_upload_and_complete(self, client: TestClient, app: FastAPI, settings) -> None:
        resp = upload(client, ALICE)
        assert resp.status_code == 201
        audit_id = resp.json()["audit_id"]

        status = client.get(f"/api/v1/audits/{audit_id}/status", headers=ALICE)
        assert status.status_code == 200
        body = status.json()
        assert body["status"] == "done"  # TestClient runs background task to completion
        assert body["valid_pct"] == 100.0
        assert (Path(settings.report_dir) / audit_id / "report.json").exists()

    def test_other_user_cannot_see_audit(self, client: TestClient) -> None:
        audit_id = upload(client, ALICE).json()["audit_id"]
        resp = client.get(f"/api/v1/audits/{audit_id}/status", headers=BOB)
        assert resp.status_code == 404


class TestTAPI02StatusTransitions:
    def test_lifecycle_logged_queued_processing_done(
        self, client: TestClient, app: FastAPI
    ) -> None:
        audit_id = upload(client, ALICE).json()["audit_id"]
        with app.state.session_factory() as session:
            actions = [
                e.action
                for e in session.scalars(
                    select(AuditLogEntry)
                    .where(AuditLogEntry.subject == audit_id)
                    .order_by(AuditLogEntry.id)
                )
            ]
        assert actions == ["audit.uploaded", "audit.processing", "audit.completed"]

    def test_failed_below_95_pct(self, client: TestClient) -> None:
        dirty = (FIXTURES / "mixed_dirty.jsonl").read_bytes()
        audit_id = upload(client, ALICE, data=dirty).json()["audit_id"]
        body = client.get(f"/api/v1/audits/{audit_id}/status", headers=ALICE).json()
        assert body["status"] == "failed"
        assert body["valid_pct"] == pytest.approx(92.0)
        assert "95" in body["error"]  # user-safe FR-03 message


class TestTAPI03VersionedPrefix:
    def test_api_lives_under_v1_only(self, client: TestClient) -> None:
        assert client.post("/api/audits", headers=ALICE).status_code == 404
        assert client.get("/api/v1/audits/nope/status", headers=ALICE).status_code == 404
        # and the versioned route exists (405/422/200 anything but 404 for POST path)
        assert client.post("/api/v1/audits", headers=ALICE).status_code != 404


class TestTAPI0405Idempotency:
    def test_replay_returns_original(self, client: TestClient) -> None:
        first = upload(client, ALICE, key="k-123")
        assert first.status_code == 201
        assert first.json()["replayed"] is False
        second = upload(client, ALICE, key="k-123")
        assert second.status_code == 200
        assert second.json() == {"audit_id": first.json()["audit_id"], "replayed": True}

    def test_key_is_per_user(self, client: TestClient) -> None:
        a = upload(client, ALICE, key="shared-key")
        b = upload(client, BOB, key="shared-key")
        assert a.status_code == 201 and b.status_code == 201
        assert a.json()["audit_id"] != b.json()["audit_id"]


class TestTAPI06ConcurrencyQueue:
    def test_queue_position_reported(self, client: TestClient, app: FastAPI) -> None:
        with app.state.session_factory() as session:
            user = User(email="q@example.com")
            session.add(user)
            session.flush()
            processing = Audit(user_id=user.id, status="processing")
            q1 = Audit(user_id=user.id, status="queued")
            session.add_all([processing, q1])
            session.flush()
            q2 = Audit(user_id=user.id, status="queued")
            session.add(q2)
            session.commit()
            assert queue_position(session, q1) == 1
            assert queue_position(session, q2) == 2
        h = {"X-User-Email": "q@example.com"}
        assert client.get(f"/api/v1/audits/{q1.id}/status", headers=h).json()["queue_position"] == 1
        assert client.get(f"/api/v1/audits/{q2.id}/status", headers=h).json()["queue_position"] == 2

    def test_wait_for_slot_blocks_at_cap(self, app: FastAPI, settings) -> None:
        with app.state.session_factory() as session:
            user = User(email="cap@example.com")
            session.add(user)
            session.flush()
            session.add_all(
                Audit(user_id=user.id, status="processing")
                for _ in range(settings.max_concurrent_audits)
            )
            session.commit()
        runner: AuditRunner = app.state.runner
        assert runner.wait_for_slot(timeout_s=0.3, poll_s=0.05) is False
        with app.state.session_factory() as session:
            for audit in session.scalars(select(Audit).where(Audit.status == "processing")):
                audit.status = "done"
            session.commit()
        assert runner.wait_for_slot(timeout_s=0.3, poll_s=0.05) is True


class TestTAPI07ErrorEnvelope:
    def assert_envelope(self, body: dict, code: str) -> None:
        assert set(body) == {"error"}
        assert set(body["error"]) == {"code", "message", "request_id"}  # NFR-14
        assert body["error"]["code"] == code
        assert body["error"]["request_id"]

    def test_404_envelope(self, client: TestClient) -> None:
        resp = client.get("/api/v1/audits/missing/status", headers=ALICE)
        assert resp.status_code == 404
        self.assert_envelope(resp.json(), "not_found")

    def test_401_envelope(self, client: TestClient) -> None:
        resp = client.get("/api/v1/audits/x/status")
        assert resp.status_code == 401
        self.assert_envelope(resp.json(), "unauthorized")

    def test_422_envelope_missing_file(self, client: TestClient) -> None:
        resp = client.post("/api/v1/audits", headers=ALICE)
        assert resp.status_code == 422
        self.assert_envelope(resp.json(), "validation_error")

    def test_400_envelope_bad_extension(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/audits",
            headers=ALICE,
            files={"file": ("logs.txt", io.BytesIO(b"x"), "text/plain")},
        )
        assert resp.status_code == 400
        self.assert_envelope(resp.json(), "bad_request")


class TestTNFR03And12RateLimits:
    def test_burst_hits_429_with_retry_after(self, client: TestClient) -> None:
        last = None
        for _ in range(11):
            last = upload(client, ALICE)
        assert last is not None and last.status_code == 429  # T-NFR-03
        assert "Retry-After" in last.headers  # NFR-12
        body = last.json()
        assert body["error"]["code"] == "rate_limited"

    def test_limit_keyed_per_user_not_ip(self, client: TestClient) -> None:
        for _ in range(11):
            resp = upload(client, ALICE)
        assert resp.status_code == 429
        # same client (same IP): a different authenticated user is NOT limited
        assert upload(client, BOB).status_code == 201  # NFR-12 precedence

    def test_key_function_ip_fallback(self) -> None:
        class FakeRequest:
            class state:
                pass

            client = type("c", (), {"host": "10.9.8.7"})()
            headers: typing.ClassVar[dict[str, str]] = {}

        key = user_or_ip_key(FakeRequest())  # type: ignore[arg-type]
        assert key == "ip:10.9.8.7"
