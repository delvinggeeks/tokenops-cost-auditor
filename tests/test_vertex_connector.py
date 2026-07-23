"""WP-CLOUD-T2 C-C tests — the Google Vertex AI connector.

Fixture-driven (no live calls, no real signing): a fake HTTP serves the
canned OAuth token exchange and Cloud Monitoring timeSeries response. Pins:
credential parse (SA JSON) + partial refusal, model normalization, the
input/output token split → prompt/completion (cached 0 by construction),
typed auth refusals with Google-worded verdicts, the registry pull, d2
cache-blindness on vertex-ai, and the wizard journey.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Base, Source, SourceUsage, User
from tokenops_cost_auditor.services.connectors import validate, vertex_usage
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError
from tokenops_cost_auditor.services.connectors.pull import run_pull
from tokenops_cost_auditor.services.connectors.source_audit import active_detectors, coverage_rows

EMAIL = "vertex-owner@example.com"
HDR = {"X-User-Email": EMAIL}

# a syntactically-valid RSA key so the RS256 signing path actually runs
_TEST_PRIVATE_KEY = None


def _gen_key() -> str:
    global _TEST_PRIVATE_KEY
    if _TEST_PRIVATE_KEY is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _TEST_PRIVATE_KEY = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    return _TEST_PRIVATE_KEY


def cred_blob() -> str:
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "my-project",
            "private_key": _gen_key(),
            "client_email": "reader@my-project.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        sort_keys=True,
    )


def _series(model: str, kind: str, points: list[tuple[str, int]]) -> dict[str, Any]:
    return {
        "metric": {"labels": {"type": kind}},
        "resource": {"labels": {"model_user_id": model}},
        "points": [
            {"interval": {"endTime": ts}, "value": {"int64Value": str(v)}} for ts, v in points
        ],
    }


METRICS = {
    "timeSeries": [
        _series(
            "gemini-2.5-pro",
            "input",
            [("2026-07-20T00:00:00Z", 100000), ("2026-07-21T00:00:00Z", 50000)],
        ),
        _series("gemini-2.5-pro", "output", [("2026-07-20T00:00:00Z", 8000)]),
        _series("gemini-1.5-flash-002", "input", [("2026-07-20T00:00:00Z", 4000)]),
        _series("gemini-1.5-flash-002", "output", [("2026-07-20T00:00:00Z", 200)]),
    ]
}


class FakeResp:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class FakeGoogle:
    def __init__(self, token_status: int = 200, metrics_status: int = 200) -> None:
        self.token_status = token_status
        self.metrics_status = metrics_status
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, *, data: Any) -> FakeResp:
        self.posts.append({"url": url, "data": data})
        if self.token_status != 200:
            return FakeResp({}, self.token_status)
        return FakeResp({"access_token": "ya29.fake"})

    def get(self, url: str, *, params: Any, headers: Any) -> FakeResp:
        self.gets.append({"url": url, "params": params, "headers": headers})
        if self.metrics_status != 200:
            return FakeResp({}, self.metrics_status)
        return FakeResp(METRICS)


@pytest.fixture()
def bare_settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/v.db", _env_file=None)


@pytest.fixture()
def session(bare_settings: Settings) -> Session:  # type: ignore[name-defined] # noqa: F821
    engine = create_engine(bare_settings.database_url)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session as _S

    return _S(engine)


class TestCredentialAndNormalization:
    def test_01_parse_refuses_partial_and_nonjson(self) -> None:
        assert vertex_usage.parse_credential(cred_blob())["project_id"] == "my-project"
        with pytest.raises(ConnectorAuthError):
            vertex_usage.parse_credential(json.dumps({"project_id": "x"}))  # missing fields
        with pytest.raises(ConnectorAuthError):
            vertex_usage.parse_credential("not json")

    def test_02_model_normalization(self) -> None:
        n = vertex_usage.normalize_model_id
        assert n("gemini-1.5-flash-002") == "gemini-1.5-flash"
        assert n("gemini-2.5-pro") == "gemini-2.5-pro"
        assert n("publishers/google/models/gemini-2.5-flash-001") == "gemini-2.5-flash"


class TestParseAndFetch:
    def test_03_input_output_split_counts_only(self) -> None:
        buckets = vertex_usage.parse_series(METRICS)
        by = {(b["day"].isoformat(), b["model"]): b for b in buckets}
        pro = by[("2026-07-20", "gemini-2.5-pro")]
        assert pro["prompt_tokens"] == 100000 and pro["completion_tokens"] == 8000
        assert pro["cached_tokens"] == 0  # by construction — no cache split
        assert by[("2026-07-20", "gemini-1.5-flash")]["prompt_tokens"] == 4000  # normalized
        assert all(
            set(b)
            == {"day", "model", "calls", "prompt_tokens", "completion_tokens", "cached_tokens"}
            for b in buckets
        )

    def test_04_fetch_signs_and_queries(self) -> None:
        http = FakeGoogle()
        buckets, pages = vertex_usage.fetch_usage(
            cred_blob(), date(2026, 7, 20), date(2026, 7, 21), http
        )
        assert pages == 1 and len(buckets) == 3
        # a real RS256 assertion was built and posted to the token_uri
        assert http.posts[0]["data"]["assertion"].count(".") == 2
        assert "monitoring.googleapis.com" in http.gets[0]["url"]
        assert http.gets[0]["headers"]["Authorization"] == "Bearer ya29.fake"

    def test_04b_follows_next_page_token(self) -> None:
        """cold-review f.1: a paged response must be fully read, not
        truncated at page 1 (the Bedrock chunk lesson)."""

        class PagingGoogle(FakeGoogle):
            def __init__(self) -> None:
                super().__init__()
                self.page = 0

            def get(self, url: str, *, params: Any, headers: Any) -> FakeResp:
                self.gets.append({"params": params})
                self.page += 1
                if self.page == 1:
                    return FakeResp(
                        {
                            "timeSeries": [
                                _series(
                                    "gemini-2.5-pro", "input", [("2026-07-20T00:00:00Z", 30000)]
                                )
                            ],
                            "nextPageToken": "pg2",
                        }
                    )
                # page 2: MORE input tokens for the same (day, model) — must merge
                return FakeResp(
                    {
                        "timeSeries": [
                            _series("gemini-2.5-pro", "input", [("2026-07-20T00:00:00Z", 20000)])
                        ]
                    }
                )

        http = PagingGoogle()
        buckets, pages = vertex_usage.fetch_usage(
            cred_blob(), date(2026, 7, 20), date(2026, 7, 20), http
        )
        assert pages == 2  # both pages read
        assert http.gets[1]["params"]["pageToken"] == "pg2"  # token followed
        pro = next(b for b in buckets if b["model"] == "gemini-2.5-pro")
        assert pro["prompt_tokens"] == 50000  # 30000 + 20000 merged across pages

    def test_04c_int64_string_precision(self) -> None:
        """cold-review f.3: int64Value is a string precisely to avoid float
        rounding on large counts — parse it as an int, not through float."""
        payload = {
            "timeSeries": [
                {
                    "metric": {"labels": {"type": "input"}},
                    "resource": {"labels": {"model_user_id": "gemini-2.5-pro"}},
                    "points": [
                        {
                            "interval": {"endTime": "2026-07-20T00:00:00Z"},
                            "value": {"int64Value": "9007199254740993"},
                        }
                    ],
                }
            ]
        }
        b = vertex_usage.parse_series(payload)[0]
        assert b["prompt_tokens"] == 9007199254740993  # exact, not float-mangled

    def test_05_auth_refusals_typed(self) -> None:
        with pytest.raises(ConnectorAuthError) as e:
            vertex_usage.fetch_usage(
                cred_blob(), date(2026, 7, 20), date(2026, 7, 21), FakeGoogle(token_status=401)
            )
        assert e.value.status == 401
        with pytest.raises(ConnectorAuthError) as e2:
            vertex_usage.fetch_usage(
                cred_blob(), date(2026, 7, 20), date(2026, 7, 21), FakeGoogle(metrics_status=403)
            )
        assert e2.value.status == 403


class TestRegistryPull:
    def test_06_run_pull_upserts_vertex_buckets(
        self, session: Any, bare_settings: Settings
    ) -> None:
        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        src = Source(
            user_id=user.id,
            provider="vertex-ai",
            label="vertex-ai usage",
            credentials_encrypted=encrypt_credential(bare_settings.secret_key, cred_blob()),
        )
        session.add(src)
        session.commit()
        stats = run_pull(session, bare_settings, src, FakeGoogle())
        session.commit()
        assert stats.upserted == 3
        rows = session.execute(select(SourceUsage)).scalars().all()
        assert {r.model for r in rows} == {"gemini-2.5-pro", "gemini-1.5-flash"}
        assert all(r.cached_tokens == 0 for r in rows)

    def test_06b_source_audit_prices_gemini_end_to_end(
        self, session: Any, bare_settings: Settings
    ) -> None:
        """system-tester suggestion: money-math honesty end to end — a fresh
        Vertex source must PRICE gemini-2.5-pro (a priced row), not list it
        unpriced, and produce a nonzero as-billed spend."""
        from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit
        from tokenops_cost_auditor.services.pricing.table import PricingTable

        user = User(email="vertex-price@example.com")
        session.add(user)
        session.flush()
        src = Source(
            user_id=user.id,
            provider="vertex-ai",
            label="vertex-ai usage",
            credentials_encrypted=encrypt_credential(bare_settings.secret_key, cred_blob()),
        )
        session.add(src)
        session.commit()
        run_pull(session, bare_settings, src, FakeGoogle())
        session.commit()
        audit_id = run_source_audit(session, bare_settings, PricingTable.load(), src)
        session.commit()
        from tokenops_cost_auditor.persistence.models import Audit

        audit = session.get(Audit, audit_id)
        assert audit is not None
        assert float(audit.total_spend_usd or 0) > 0  # gemini-2.5-pro priced, not unpriced


class TestCacheBlindHonesty:
    def test_07_d2_not_run_on_vertex(self) -> None:
        assert "d2_missing_cache" not in active_detectors("vertex-ai")
        rows = {str(r["detector"]): r for r in coverage_rows("vertex-ai")}
        assert rows["d2_missing_cache"]["status"] == "not_observable"


class TestValidationVerdicts:
    def test_08_ok_bad_and_role_wordings(self) -> None:
        assert validate.validate_key("vertex-ai", cred_blob(), FakeGoogle()).status == validate.OK
        bad = validate.validate_key("vertex-ai", cred_blob(), FakeGoogle(token_status=400))
        assert bad.status == validate.BAD_KEY and "service-account key" in bad.detail
        role = validate.validate_key("vertex-ai", cred_blob(), FakeGoogle(metrics_status=403))
        assert role.status == validate.NO_SCOPE and "Monitoring Viewer" in role.detail


class TestWizardJourney:
    def test_09_wizard_textarea_and_switch_links(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "Connect Google Vertex AI" in client.get("/sources", headers=HDR).text
        page = client.get("/sources/connect/vertex-ai", headers=HDR)
        assert page.status_code == 200
        assert 'name="service_account"' in page.text and "<textarea" in page.text
        assert "Monitoring Viewer" in page.text
        assert "not observable on Vertex" in page.text  # cache honesty before connect

    def test_10_validate_stores_sa_json_and_dedupes(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tokenops_cost_auditor.web import routes_sources

        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        with app.state.session_factory() as s:
            from tokenops_cost_auditor.persistence.models import Subscription

            user = s.execute(select(User).where(User.email == EMAIL)).scalar_one()
            s.add(Subscription(user_id=user.id, provider="manual", plan="team"))
            s.commit()
        monkeypatch.setattr(
            routes_sources.validate,
            "validate_key",
            lambda *a, **k: validate.VERDICTS[validate.UNREACHABLE],
        )
        blob = cred_blob()
        resp = client.post(
            "/sources/connect/vertex-ai/validate", data={"service_account": blob}, headers=HDR
        )
        assert resp.status_code == 200
        with app.state.session_factory() as s:
            from tokenops_cost_auditor.services.connectors.crypto import decrypt_credential

            src = s.execute(select(Source).where(Source.provider == "vertex-ai")).scalar_one()
            stored = json.loads(
                decrypt_credential(app.state.settings.secret_key, src.credentials_encrypted)
            )
            assert stored["project_id"] == "my-project"
        dup = client.post(
            "/sources/connect/vertex-ai/validate", data={"service_account": blob}, headers=HDR
        )
        assert dup.status_code == 409  # same SA json → same fingerprint

    def test_11_malformed_json_refused(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        resp = client.post(
            "/sources/connect/vertex-ai/validate",
            data={"service_account": "{not valid json"},
            headers=HDR,
        )
        assert resp.status_code == 400
