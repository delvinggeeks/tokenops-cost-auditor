"""WP-CC-LINK — the collector's laws, walked end to end (R-VERTICAL).

- R-CC-LINK 2: ONE HUMAN ACTION IS THE FLOOR — the server half refuses a
  link without consent; consent is NOT NULL on the device row by schema.
- Tokens hashed at rest (keyed fingerprint); plaintext only in the reply.
- Ships enter the T1 pipeline (FR-26 idempotent; paid_via=collector;
  device-grade source attribution) and pause honestly when the plan lapses.
- Revoke is immediate; the machines surface tells the truth.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, Device, LinkCode, Subscription, User

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}
FIXTURE = Path(__file__).parent / "fixtures" / "waste_pack_anthropic.jsonl"


def grant(app: FastAPI, plan: str = "pro") -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan=plan))
        session.commit()
        return user.id


def issue_code(client: TestClient) -> str:
    resp = client.post("/sources/claude-code/code", headers=HDR)
    assert resp.status_code == 200
    import re

    m = re.search(r"link ([A-Za-z0-9_\-]+) --server", resp.text)
    assert m, "code not rendered in the partial"
    return m.group(1)


def link(client: TestClient, code: str, consent: bool = True, host: str = "dev-laptop"):
    return client.post(
        "/api/v1/collector/link",
        json={"code": code, "hostname": host, "consent": consent},
    )


class TestConsentFloor:
    def test_01_link_refuses_without_consent(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        code = issue_code(client)
        refused = link(client, code, consent=False)
        assert refused.status_code == 400
        assert "consent required" in refused.json()["error"]["message"]  # NFR-14 envelope
        with app.state.session_factory() as session:
            assert session.execute(select(Device)).scalars().all() == []
            # and the code survives for a consenting retry
            row = session.execute(select(LinkCode)).scalars().one()
            assert row.consumed_at is None

    def test_02_free_plan_cannot_issue_codes(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # creates the free account
        resp = client.post("/sources/claude-code/code", headers=HDR)
        assert resp.status_code == 403
        assert "Pro" in resp.json()["detail"]


class TestLinkShipJourney:
    def test_03_full_journey_link_ship_audit_list_revoke(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        code = issue_code(client)
        linked = link(client, code)
        assert linked.status_code == 201
        token = linked.json()["device_token"]
        with app.state.session_factory() as session:
            device = session.execute(select(Device)).scalars().one()
            assert device.consent_at is not None  # the recorded human moment
            assert device.token_hash != token and token not in device.token_hash
        # the machine appears on Sources
        page = client.get("/sources", headers=HDR)
        assert "dev-laptop" in page.text and "never" in page.text
        # ship counts → a real audit through the T1 pipeline
        shipped = client.post(
            "/api/v1/collector/ship",
            files={"file": ("collector.jsonl", FIXTURE.read_bytes(), "application/json")},
            headers={"X-Device-Token": token, "Idempotency-Key": "idem-1"},
        )
        assert shipped.status_code == 201
        audit_id = shipped.json()["audit_id"]
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            assert audit.paid_via == "collector"
            assert audit.source_id is not None  # device-grade attribution
            assert audit.status == "done"  # background ran in-line under TestClient
            device = session.execute(select(Device)).scalars().one()
            assert device.last_ship_at is not None
        # FR-26: the cron re-ship of identical content replays, never duplicates
        again = client.post(
            "/api/v1/collector/ship",
            files={"file": ("collector.jsonl", FIXTURE.read_bytes(), "application/json")},
            headers={"X-Device-Token": token, "Idempotency-Key": "idem-1"},
        )
        assert again.status_code == 200 and again.json()["replayed"] is True
        # revoke → immediate refusal, past audit stays
        with app.state.session_factory() as session:
            device_id = session.execute(select(Device)).scalars().one().id
        assert (
            client.post(
                f"/sources/devices/{device_id}/revoke", headers=HDR, follow_redirects=False
            ).status_code
            == 303
        )
        dead = client.post(
            "/api/v1/collector/ship",
            files={"file": ("c.jsonl", FIXTURE.read_bytes(), "application/json")},
            headers={"X-Device-Token": token},
        )
        assert dead.status_code == 401
        with app.state.session_factory() as session:
            assert session.get(Audit, audit_id) is not None  # history is the customer's
            dead_device = session.execute(select(Device)).scalars().one()
            assert dead_device.token_hash is None  # key material DELETED on revoke

    def test_04_expired_and_reused_codes_refused_plainly(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        code = issue_code(client)
        with app.state.session_factory() as session:
            row = session.execute(select(LinkCode)).scalars().one()
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.commit()
        assert link(client, code).status_code == 410
        code2 = issue_code(client)
        assert link(client, code2).status_code == 201
        assert link(client, code2).status_code == 404  # one-shot

    def test_05_lapsed_plan_pauses_ships_honestly(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = link(client, issue_code(client)).json()["device_token"]
        with app.state.session_factory() as session:
            sub = session.execute(select(Subscription)).scalars().one()
            sub.status = "cancelled"
            session.commit()
        resp = client.post(
            "/api/v1/collector/ship",
            files={"file": ("c.jsonl", FIXTURE.read_bytes(), "application/json")},
            headers={"X-Device-Token": token},
        )
        assert resp.status_code == 402
        assert "pause" in resp.json()["error"]["message"]  # NFR-14 envelope


class TestCliConsent:
    def test_06_cli_link_refuses_noninteractive_and_disagreement(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The CLI half of the floor: no TTY = no link; wrong words = no link;
        nothing is sent either way (urlopen would explode if called)."""
        import sys

        from tokenops_cost_auditor import cli

        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("network before consent")),
        )
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert cli._cmd_link("code123", "https://example.test") == 2
        assert "needs a person" in capsys.readouterr().out
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt="": "no thanks")
        assert cli._cmd_link("code123", "https://example.test") == 2
        assert "not linked" in capsys.readouterr().out
