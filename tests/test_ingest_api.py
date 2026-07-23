"""S-0 tests (R-SDK-PLATFORM) — the ingest DSN, end to end.

Pins: the mint→POST→audit→report journey (the S-0 DoD), the FR-22 door
(strict allowlist, offenders NAMED, oversized strings refused), FR-26
idempotency, plan gating both halves, revoke-deletes-the-hash (authority
law), write-only trust boundary, explorer/runs attribution, R-NAMING in
the shown-once reveal.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, IngestKey, Subscription, User

EMAIL = "sdk-owner@example.com"


def err(resp) -> str:
    """NFR-14: /api/v1 errors arrive in the {error:{message}} envelope."""
    return str(resp.json()["error"]["message"])


HDR = {"X-User-Email": EMAIL}

RECORDS = [
    {
        "ts": f"2026-07-{10 + i:02d}T10:00:00Z",
        "provider": "openai",
        "model": "gpt-5.4",
        "prompt_tokens": 3000 + i,
        "completion_tokens": 50,
        "cached_tokens": 0,
        "latency_ms": 812.5,
        "tag": "summarizer",
    }
    for i in range(8)
]


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


def mint(client: TestClient, label: str = "prod api") -> str:
    resp = client.post("/sources/sdk/key", data={"label": label}, headers=HDR)
    assert resp.status_code == 200
    m = re.search(r"Bearer (ik_[A-Za-z0-9_\-]+)", resp.text)
    assert m, "full token not rendered in the reveal"
    return m.group(1)


class TestMint:
    def test_01_free_plan_gated_with_billing_pointer(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        resp = client.post("/sources/sdk/key", data={"label": "x"}, headers=HDR)
        assert resp.status_code == 403 and "/billing" in resp.json()["detail"]

    def test_02_reveal_carries_full_dsn_once_and_stores_hash_only(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        resp = client.post("/sources/sdk/key", data={"label": "prod api"}, headers=HDR)
        assert resp.status_code == 200
        squashed = re.sub(r"\s+", " ", resp.text)
        # R-NAMING: the full env var name, and the DSN carries key@host uncut
        assert "TOKENOPS_COST_AUDITOR_DSN=" in squashed
        token = re.search(r"Bearer (ik_[A-Za-z0-9_\-]+)", resp.text).group(1)  # type: ignore[union-attr]
        assert f"{token}@" in squashed  # DSN form https://<key>@<host>
        with app.state.session_factory() as session:
            row = session.execute(select(IngestKey)).scalar_one()
            assert row.key_hash is not None and token not in row.key_hash
            assert row.label == "prod api"


class TestJourney:
    def test_03_mint_post_audit_report(self, app: FastAPI) -> None:
        """The S-0 DoD: mint → POST a batch → audit lands → report reachable."""
        grant(app)
        client = TestClient(app)
        token = mint(client)
        resp = client.post(
            "/api/v1/ingest",
            json={"records": RECORDS},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "batch-1"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["records"] == len(RECORDS) and body["replayed"] is False
        with app.state.session_factory() as session:
            audit = session.get(Audit, body["audit_id"])
            assert audit is not None
            assert audit.status == "done"  # background ran in-line under TestClient
            assert audit.paid_via == "sdk"
            assert audit.source_id is not None  # attributed to the key
        # the run is on the ledger with its honest trigger
        runs = client.get("/runs", headers=HDR)
        assert "SDK ingest" in runs.text
        # the key appears in the explorer's source selector
        explore = client.get("/explore", headers=HDR)
        assert "prod api (SDK)" in explore.text
        # last_used stamped on Sources
        sources = client.get("/sources", headers=HDR)
        assert "never — nothing shipped yet" not in sources.text

    def test_04_idempotent_replay(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint(client)
        h = {"Authorization": f"Bearer {token}", "Idempotency-Key": "batch-dup"}
        first = client.post("/api/v1/ingest", json={"records": RECORDS}, headers=h)
        second = client.post("/api/v1/ingest", json={"records": RECORDS}, headers=h)
        assert first.status_code == 201 and second.status_code == 200
        assert second.json() == {"audit_id": first.json()["audit_id"], "replayed": True}


class TestFR22Door:
    def test_05_text_fields_rejected_by_name(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint(client)
        bad = dict(RECORDS[0])
        bad["prompt"] = "the actual prompt text"
        bad["messages"] = [{"role": "user", "content": "hi"}]
        resp = client.post(
            "/api/v1/ingest",
            json={"records": [bad]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        detail = err(resp)
        assert "messages" in detail and "prompt" in detail  # offenders NAMED
        assert "FR-22" in detail or "counts-only" in detail
        with app.state.session_factory() as session:
            assert session.execute(select(Audit)).scalar_one_or_none() is None  # nothing stored

    def test_06_oversized_strings_and_missing_fields_refused(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint(client)
        h = {"Authorization": f"Bearer {token}"}
        smuggle = dict(RECORDS[0], tag="x" * 4000)  # text smuggled into a bounded field
        resp = client.post("/api/v1/ingest", json={"records": [smuggle]}, headers=h)
        assert resp.status_code == 422 and "tag" in err(resp)
        resp = client.post(
            "/api/v1/ingest",
            json={"records": [{"ts": "2026-07-23T00:00:00Z"}]},
            headers=h,
        )
        assert resp.status_code == 422 and "missing" in err(resp)
        resp = client.post("/api/v1/ingest", json={"records": []}, headers=h)
        assert resp.status_code == 422

    def test_06b_empty_required_and_huge_counts_refused(self, app: FastAPI) -> None:
        """cold-review f.1/f.2: an empty required field would 201 at the door
        then fail every row downstream; an absurd count would distort totals.
        Both must be refused BEFORE anything is stored."""
        grant(app)
        client = TestClient(app)
        token = mint(client)
        h = {"Authorization": f"Bearer {token}"}
        empty = dict(RECORDS[0], provider="")  # present but empty
        resp = client.post("/api/v1/ingest", json={"records": [empty]}, headers=h)
        assert resp.status_code == 422 and "provider" in err(resp)
        huge = dict(RECORDS[0], prompt_tokens=10**18)
        resp = client.post("/api/v1/ingest", json={"records": [huge]}, headers=h)
        assert resp.status_code == 422 and "prompt_tokens" in err(resp)
        with app.state.session_factory() as session:
            assert session.execute(select(Audit)).scalar_one_or_none() is None  # nothing stored

    def test_06c_key_cap_enforced(self, app: FastAPI) -> None:
        """cold-review f.3: the row-locked mint cap holds. Seed keys via ORM
        (the 5/min mint limit is a separate control), then the next mint 403s."""
        from tokenops_cost_auditor.web.routes_ingest import MAX_KEYS_PER_USER

        uid = grant(app)
        with app.state.session_factory() as session:
            for i in range(MAX_KEYS_PER_USER):
                session.add(IngestKey(user_id=uid, label=f"k{i}", key_hash=f"hash-{i}"))
            session.commit()
        over = TestClient(app).post("/sources/sdk/key", data={"label": "one too many"}, headers=HDR)
        assert over.status_code == 403 and "limit" in over.json()["detail"]


class TestAuthority:
    def test_07_revoke_deletes_hash_and_stops_ingest(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint(client)
        with app.state.session_factory() as session:
            key_id = session.execute(select(IngestKey)).scalar_one().id
        resp = client.post(f"/sources/sdk/{key_id}/revoke", headers=HDR, follow_redirects=False)
        assert resp.status_code == 303
        with app.state.session_factory() as session:
            row = session.get(IngestKey, key_id)
            assert row is not None and row.key_hash is None  # key material GONE
            assert row.revoked_at is not None
        after = client.post(
            "/api/v1/ingest",
            json={"records": RECORDS},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert after.status_code == 401

    def test_08_bad_or_missing_auth_refused(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert client.post("/api/v1/ingest", json={"records": RECORDS}).status_code == 401
        assert (
            client.post(
                "/api/v1/ingest",
                json={"records": RECORDS},
                headers={"Authorization": "Bearer ik_never-minted"},
            ).status_code
            == 401
        )

    def test_09_lapsed_plan_pauses_ingest_honestly(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint(client)
        with app.state.session_factory() as session:
            sub = session.execute(select(Subscription)).scalars().one()
            sub.status = "cancelled"
            session.commit()
        resp = client.post(
            "/api/v1/ingest",
            json={"records": RECORDS},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402 and "pause" in err(resp)


class TestRateAndDsnHardening:
    def test_10_scheme_less_host_still_embeds_the_token(self, app: FastAPI) -> None:
        """cold-review f.4 (re-gate proof): a base URL configured without a
        scheme must NOT silently drop the token from the shown-once DSN."""
        grant(app)
        app.state.settings.app_base_url = "tokenops-cost-auditor.com"  # no scheme
        resp = TestClient(app).post("/sources/sdk/key", data={"label": "prod"}, headers=HDR)
        assert resp.status_code == 200
        token = re.search(r"Bearer (ik_[A-Za-z0-9_\-]+)", resp.text).group(1)  # type: ignore[union-attr]
        squashed = re.sub(r"\s+", " ", resp.text)
        assert f"https://{token}@tokenops-cost-auditor.com" in squashed  # token embedded, uncut

    def test_11_rate_key_buckets_per_token_and_falls_to_ip(self) -> None:
        """cold-review f.5 (re-gate proof): distinct tokens get distinct
        fairness buckets; anything not a well-formed ingest token falls to
        IP so a bad-token flood can't mint unlimited buckets. The stacked
        per-IP ceiling (_INGEST_IP_LIMIT) is the real abuse bound."""
        from starlette.requests import Request

        from tokenops_cost_auditor.web.routes_ingest import _INGEST_IP_LIMIT, _ingest_rate_key

        def req(auth: str | None) -> Request:
            headers = [(b"authorization", auth.encode())] if auth else []
            return Request({"type": "http", "headers": headers, "client": ("9.9.9.9", 1234)})

        a = _ingest_rate_key(req("Bearer ik_aaaaaaaa"))
        b = _ingest_rate_key(req("Bearer ik_bbbbbbbb"))
        assert a != b and a.startswith("ingest:")  # distinct per-key buckets
        assert _ingest_rate_key(req(None)).startswith("ip:")  # no token → IP
        assert _ingest_rate_key(req("Bearer sk-not-ours")).startswith("ip:")  # wrong prefix → IP
        assert _INGEST_IP_LIMIT.endswith("/minute")  # the abuse ceiling exists
