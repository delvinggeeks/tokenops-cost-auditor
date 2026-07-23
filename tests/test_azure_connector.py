"""WP-CLOUD-T2 C-A tests — the Azure OpenAI connector, end to end.

Fixture-driven (no live calls): a fake HTTP client serves the canned Entra
token exchange and Azure Monitor metrics payloads. Pins: credential packing
and refusal of partial grants, metric merge with cached_tokens=0 by
construction (FR-22 counts only), the registry pull path, Azure-worded
validation verdicts, and the R-Q1 cache-blindness honesty (d2 never runs
against fabricated zeros; coverage says "not observable on Azure").
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Base, Source, SourceUsage, User
from tokenops_cost_auditor.services.connectors import azure_usage, validate
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError
from tokenops_cost_auditor.services.connectors.pull import run_pull
from tokenops_cost_auditor.services.connectors.source_audit import (
    active_detectors,
    coverage_rows,
)

EMAIL = "azure-owner@example.com"
HDR = {"X-User-Email": EMAIL}

RESOURCE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/ai"
    "/providers/Microsoft.CognitiveServices/accounts/prod-openai"
)
CRED = {
    "tenant_id": "11111111-1111-1111-1111-111111111111",
    "client_id": "22222222-2222-2222-2222-222222222222",
    "client_secret": "shh-secret-value",
    "resource_id": RESOURCE_ID,
}
CRED_BLOB = json.dumps(CRED, sort_keys=True)


def _series(model: str, points: list[tuple[str, float]]) -> dict[str, Any]:
    return {
        "metadatavalues": [{"name": {"value": "modelname"}, "value": model}],
        "data": [{"timeStamp": ts, "total": total} for ts, total in points],
    }


METRICS_PAYLOAD = {
    "value": [
        {
            "name": {"value": "ProcessedPromptTokens"},
            "timeseries": [
                _series(
                    "gpt-5.4",
                    [("2026-07-20T00:00:00Z", 100000.0), ("2026-07-21T00:00:00Z", 50000.0)],
                ),
                _series("gpt-5.4-mini", [("2026-07-20T00:00:00Z", 400000.0)]),
            ],
        },
        {
            "name": {"value": "GeneratedTokens"},
            "timeseries": [
                _series(
                    "gpt-5.4", [("2026-07-20T00:00:00Z", 8000.0), ("2026-07-21T00:00:00Z", 4000.0)]
                ),
                _series("gpt-5.4-mini", [("2026-07-20T00:00:00Z", 30000.0)]),
            ],
        },
        {
            "name": {"value": "AzureOpenAIRequests"},
            "timeseries": [
                _series(
                    "gpt-5.4", [("2026-07-20T00:00:00Z", 120.0), ("2026-07-21T00:00:00Z", 60.0)]
                ),
                _series("gpt-5.4-mini", [("2026-07-20T00:00:00Z", 900.0)]),
            ],
        },
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


class FakeAzure:
    """Canned Entra token endpoint + metrics endpoint."""

    def __init__(self, token_status: int = 200, metrics_status: int = 200) -> None:
        self.token_status = token_status
        self.metrics_status = metrics_status
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, *, data: Any) -> FakeResp:
        self.posts.append({"url": url, "data": data})
        if self.token_status != 200:
            return FakeResp({}, self.token_status)
        return FakeResp({"access_token": "tok-123"})

    def get(self, url: str, *, params: Any, headers: Any) -> FakeResp:
        self.gets.append({"url": url, "params": params, "headers": headers})
        if self.metrics_status != 200:
            return FakeResp({}, self.metrics_status)
        return FakeResp(METRICS_PAYLOAD)


@pytest.fixture()
def bare_settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/a.db", _env_file=None)


@pytest.fixture()
def session(bare_settings: Settings) -> Session:
    engine = create_engine(bare_settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


class TestCredential:
    def test_01_parse_roundtrip_and_partial_refusal(self) -> None:
        assert azure_usage.parse_credential(CRED_BLOB)["resource_id"] == RESOURCE_ID
        with pytest.raises(ConnectorAuthError):
            azure_usage.parse_credential(json.dumps({**CRED, "client_secret": ""}))
        with pytest.raises(ConnectorAuthError):
            azure_usage.parse_credential("not-json")


class TestMetricsParse:
    def test_02_merge_on_day_model_counts_only(self) -> None:
        buckets = azure_usage.parse_metrics(METRICS_PAYLOAD)
        assert [(b["day"].isoformat(), b["model"]) for b in buckets] == [
            ("2026-07-20", "gpt-5.4"),
            ("2026-07-20", "gpt-5.4-mini"),
            ("2026-07-21", "gpt-5.4"),
        ]
        first = buckets[0]
        assert (first["calls"], first["prompt_tokens"], first["completion_tokens"]) == (
            120,
            100000,
            8000,
        )
        # FR-22 + the Azure blindness bound: counts only, cached 0 by construction.
        assert all(b["cached_tokens"] == 0 for b in buckets)
        assert all(
            set(b)
            == {"day", "model", "calls", "prompt_tokens", "completion_tokens", "cached_tokens"}
            for b in buckets
        )

    def test_03_fetch_exchanges_token_then_queries_metrics(self) -> None:
        http = FakeAzure()
        buckets, pages = azure_usage.fetch_usage(
            CRED_BLOB, date(2026, 7, 20), date(2026, 7, 21), http
        )
        assert pages == 1 and len(buckets) == 3
        assert http.posts[0]["data"]["scope"] == "https://management.azure.com/.default"
        assert CRED["tenant_id"] in http.posts[0]["url"]
        get = http.gets[0]
        assert RESOURCE_ID in get["url"] and get["headers"]["Authorization"] == "Bearer tok-123"
        assert get["params"]["metricnames"] == azure_usage.METRIC_NAMES

    def test_04_auth_refusals_are_typed(self) -> None:
        with pytest.raises(ConnectorAuthError) as e400:
            azure_usage.fetch_usage(
                CRED_BLOB, date(2026, 7, 20), date(2026, 7, 21), FakeAzure(token_status=400)
            )
        assert e400.value.status == 400
        with pytest.raises(ConnectorAuthError) as e403:
            azure_usage.fetch_usage(
                CRED_BLOB, date(2026, 7, 20), date(2026, 7, 21), FakeAzure(metrics_status=403)
            )
        assert e403.value.status == 403


class TestRegistryPull:
    def test_05_run_pull_upserts_azure_buckets(
        self, session: Session, bare_settings: Settings
    ) -> None:
        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        src = Source(
            user_id=user.id,
            provider="azure-openai",
            label="azure-openai usage",
            credentials_encrypted=encrypt_credential(bare_settings.secret_key, CRED_BLOB),
        )
        session.add(src)
        session.commit()
        stats = run_pull(session, bare_settings, src, FakeAzure())
        session.commit()
        assert (stats.buckets_in, stats.upserted) == (3, 3)
        rows = session.execute(select(SourceUsage)).scalars().all()
        assert {r.model for r in rows} == {"gpt-5.4", "gpt-5.4-mini"}
        assert all(r.cached_tokens == 0 for r in rows)


class TestValidationVerdicts:
    def test_06_ok_bad_and_role_wordings(self) -> None:
        ok = validate.validate_key("azure-openai", CRED_BLOB, FakeAzure())
        assert ok.status == validate.OK
        bad = validate.validate_key("azure-openai", CRED_BLOB, FakeAzure(token_status=400))
        assert bad.status == validate.BAD_KEY and "client secret" in bad.detail
        role = validate.validate_key("azure-openai", CRED_BLOB, FakeAzure(metrics_status=403))
        assert role.status == validate.NO_SCOPE and "Monitoring Reader" in role.detail
        assert not role.can_save

    def test_07_unreachable_still_saves(self) -> None:
        class Down:
            def post(self, url: str, *, data: Any) -> FakeResp:
                raise OSError("network down")

        verdict = validate.validate_key("azure-openai", CRED_BLOB, Down())
        assert verdict.status == validate.UNREACHABLE and verdict.can_save


class TestCacheBlindHonesty:
    def test_08_d2_never_runs_on_azure_coverage_says_why(self) -> None:
        assert "d2_missing_cache" not in active_detectors("azure-openai")
        assert "d2_missing_cache" in active_detectors("openai")
        rows = {str(r["detector"]): r for r in coverage_rows("azure-openai")}
        d2 = rows["d2_missing_cache"]
        assert d2["status"] == "not_observable"
        assert "not observable on Azure" in str(d2["note"]).lower() or "Azure" in str(d2["note"])

    def test_09_aggregate_runner_skips_d2_on_azure(self, bare_settings: Settings) -> None:
        import pandas as pd

        from tokenops_cost_auditor.services.pricing.table import PricingTable
        from tokenops_cost_auditor.services.rules.aggregate import run_aggregate_detectors

        # A frame with heavy repeat traffic and ZERO cached tokens — on
        # openai this is d2 bait; on azure the zero is fabricated by the
        # platform, so d2 must not fire.
        days = [date(2026, 7, 1) + timedelta(days=i) for i in range(14)]
        frame = pd.DataFrame(
            [
                {
                    "day": d,
                    "model": "gpt-5.4",
                    "calls": 5000,
                    "prompt_tokens": 50_000_000,
                    "completion_tokens": 100_000,
                    "cached_tokens": 0,
                }
                for d in days
            ]
        )
        table = PricingTable.load()
        azure = run_aggregate_detectors(frame, "azure-openai", table, bare_settings, 14)
        assert all(f.detector != "d2_missing_cache" for f in azure)


class TestWizardJourney:
    def test_10_wizard_reachable_with_four_fields(self, app: FastAPI) -> None:
        client = TestClient(app)
        sources = client.get("/sources", headers=HDR)
        assert "Connect Azure OpenAI" in sources.text
        page = client.get("/sources/connect/azure-openai", headers=HDR)
        assert page.status_code == 200
        for field in ("tenant_id", "client_id", "client_secret", "resource_id"):
            assert f'name="{field}"' in page.text
        assert "Monitoring Reader" in page.text

    def test_11_validate_packs_four_fields_and_saves(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tokenops_cost_auditor.web import routes_sources

        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        with app.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == EMAIL)).scalar_one()
            from tokenops_cost_auditor.persistence.models import Subscription

            s.add(Subscription(user_id=user.id, provider="manual", plan="team"))
            s.commit()
        monkeypatch.setattr(
            routes_sources.validate,
            "validate_key",
            lambda *a, **k: validate.VERDICTS[validate.UNREACHABLE],
        )
        resp = client.post("/sources/connect/azure-openai/validate", data=CRED, headers=HDR)
        assert resp.status_code == 200
        with app.state.session_factory() as s:
            src = s.execute(select(Source).where(Source.provider == "azure-openai")).scalar_one()
            from tokenops_cost_auditor.services.connectors.crypto import decrypt_credential

            stored = decrypt_credential(app.state.settings.secret_key, src.credentials_encrypted)
            assert json.loads(stored) == CRED  # canonical packed JSON, all four fields
        # Same four values again = same fingerprint = the dedup guard refuses.
        dup = client.post("/sources/connect/azure-openai/validate", data=CRED, headers=HDR)
        assert dup.status_code == 409

    def test_13_real_outage_saves_through_the_live_route(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R-WIZ-DEGRADE end to end (system-tester f.3): a REAL network fault
        during validation — the HTTP client itself failing, not a stubbed
        verdict — must drive the live route to UNREACHABLE, SAVE the
        credential, and say so in the rendered words."""
        import re as _re

        class Down:
            def __init__(self, *a: Any, **k: Any) -> None: ...

            def post(self, url: str, *, data: Any) -> Any:
                raise OSError("network down")

            def get(self, url: str, *, params: Any, headers: Any) -> Any:
                raise OSError("network down")

            def close(self) -> None: ...

        monkeypatch.setattr(validate.httpx, "Client", Down)
        email = "azure-outage@example.com"
        hdr = {"X-User-Email": email}
        client = TestClient(app)
        client.get("/dashboard", headers=hdr)
        resp = client.post("/sources/connect/azure-openai/validate", data=CRED, headers=hdr)
        assert resp.status_code == 200
        squashed = _re.sub(r"\s+", " ", resp.text)
        assert "saved" in squashed.lower()  # the promise, in the rendered words
        with app.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == email)).scalar_one()
            src = s.execute(
                select(Source).where(Source.user_id == user.id, Source.provider == "azure-openai")
            ).scalar_one()  # exactly one row saved despite the outage
            assert src.status == "active"
        assert "azure-openai usage" in client.get("/sources", headers=hdr).text

    def test_14_token_less_response_is_a_credential_fault(self) -> None:
        """cold-review f.2: a 200 token response with no access_token must
        surface as the bad-credential verdict, never the role-gap one."""

        class NoToken(FakeAzure):
            def post(self, url: str, *, data: Any) -> FakeResp:
                return FakeResp({"unexpected": "shape"})

        verdict = validate.validate_key("azure-openai", CRED_BLOB, NoToken())
        assert verdict.status == validate.BAD_KEY
        assert "Monitoring Reader" not in verdict.detail

    def test_15_metric_floats_round_never_truncate(self) -> None:
        """cold-review f.1: Azure Sum aggregation returns floats; 12345.9999
        must land as 12346, not 12345."""
        payload = {
            "value": [
                {
                    "name": {"value": "ProcessedPromptTokens"},
                    "timeseries": [_series("gpt-5.4", [("2026-07-20T00:00:00Z", 12345.9999)])],
                },
                {"name": {"value": "SomethingElse"}, "timeseries": []},  # ignored
                {
                    "name": {"value": "GeneratedTokens"},
                    "timeseries": [
                        {
                            "metadatavalues": [],  # no modelname -> "unknown"
                            "data": [
                                {"timeStamp": "2026-07-20T00:00:00Z", "total": None},
                                {"timeStamp": "2026-07-21T00:00:00Z", "total": 10.4},
                            ],
                        }
                    ],
                },
            ]
        }
        buckets = azure_usage.parse_metrics(payload)
        by_key = {(b["day"].isoformat(), b["model"]): b for b in buckets}
        assert by_key[("2026-07-20", "gpt-5.4")]["prompt_tokens"] == 12346
        assert by_key[("2026-07-21", "unknown")]["completion_tokens"] == 10

    def test_12_partial_or_malformed_fields_refused(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        missing = client.post(
            "/sources/connect/azure-openai/validate",
            data={**CRED, "client_secret": ""},
            headers=HDR,
        )
        assert missing.status_code == 400
        wrong_rid = client.post(
            "/sources/connect/azure-openai/validate",
            data={**CRED, "resource_id": "/not/a/resource"},
            headers=HDR,
        )
        assert wrong_rid.status_code == 400
        assert "Resource ID" in wrong_rid.json()["detail"]
