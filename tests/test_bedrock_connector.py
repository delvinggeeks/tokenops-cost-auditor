"""WP-CLOUD-T2 C-B tests — the AWS Bedrock connector, end to end.

Fixture-driven (no live calls): a fake CloudWatch answers the SigV4-signed
JSON-protocol POSTs by routing on X-Amz-Target. Pins: credential packing
with region validation, ModelId normalization, the anthropic token
composition (prompt = input + cache_read + cache_write; cached =
cache_read), typed auth refusals with AWS-worded verdicts, the registry
pull, d2 running (Bedrock is NOT cache-blind), and the wizard journey.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Base, Source, SourceUsage, User
from tokenops_cost_auditor.services.connectors import bedrock_usage, validate
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError
from tokenops_cost_auditor.services.connectors.pull import run_pull
from tokenops_cost_auditor.services.connectors.source_audit import (
    active_detectors,
    coverage_rows,
)

EMAIL = "bedrock-owner@example.com"
HDR = {"X-User-Email": EMAIL}

CRED = {
    "access_key_id": "AKIAEXAMPLE0000000001",
    "secret_access_key": "shh-aws-secret",
    "region": "us-east-1",
}
CRED_BLOB = json.dumps(CRED, sort_keys=True)

DAY1 = int(datetime(2026, 7, 20, tzinfo=UTC).timestamp())
DAY2 = int(datetime(2026, 7, 21, tzinfo=UTC).timestamp())

# canned per-(ModelId, Metric) daily sums the fake serves
USAGE: dict[tuple[str, str], dict[int, float]] = {
    ("us.anthropic.claude-sonnet-5-v1:0", "Invocations"): {DAY1: 120.0, DAY2: 60.0},
    ("us.anthropic.claude-sonnet-5-v1:0", "InputTokenCount"): {DAY1: 40000.0, DAY2: 20000.0},
    ("us.anthropic.claude-sonnet-5-v1:0", "OutputTokenCount"): {DAY1: 2000.0, DAY2: 1000.0},
    ("us.anthropic.claude-sonnet-5-v1:0", "CacheReadInputTokens"): {DAY1: 50000.0},
    ("us.anthropic.claude-sonnet-5-v1:0", "CacheWriteInputTokens"): {DAY1: 10000.0},
    ("anthropic.claude-haiku-4-5-v1:0", "Invocations"): {DAY1: 10.0},
    ("anthropic.claude-haiku-4-5-v1:0", "InputTokenCount"): {DAY1: 1024.0},
    ("anthropic.claude-haiku-4-5-v1:0", "OutputTokenCount"): {DAY1: 256.0},
    ("anthropic.claude-haiku-4-5-v1:0", "CacheReadInputTokens"): {DAY1: 1024.0},
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


class FakeCloudWatch:
    """Routes JSON-protocol POSTs on X-Amz-Target; optional canned refusal."""

    def __init__(self, error_type: str = "", error_status: int = 0) -> None:
        self.error_type = error_type
        self.error_status = error_status
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> FakeResp:
        target = headers["X-Amz-Target"]
        payload = json.loads(content)
        self.calls.append({"url": url, "target": target, "payload": payload, "headers": headers})
        if self.error_type:
            return FakeResp({"__type": self.error_type}, self.error_status)
        if target.endswith("ListMetrics"):
            metrics = [
                {"Dimensions": [{"Name": "ModelId", "Value": mid}]}
                for mid in sorted({m for m, _ in USAGE})
            ]
            return FakeResp({"Metrics": metrics})
        if target.endswith("GetMetricData"):
            results = []
            for q in payload["MetricDataQueries"]:
                stat = q["MetricStat"]
                mid = stat["Metric"]["Dimensions"][0]["Value"]
                metric = stat["Metric"]["MetricName"]
                points = USAGE.get((mid, metric), {})
                results.append(
                    {
                        "Id": q["Id"],
                        "Timestamps": list(points.keys()),
                        "Values": list(points.values()),
                    }
                )
            return FakeResp({"MetricDataResults": results})
        raise AssertionError(f"unexpected target {target}")


@pytest.fixture()
def bare_settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/b.db", _env_file=None)


@pytest.fixture()
def session(bare_settings: Settings) -> Session:
    engine = create_engine(bare_settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


class TestCredentialAndNormalization:
    def test_01_parse_refuses_partial_and_bad_region(self) -> None:
        assert bedrock_usage.parse_credential(CRED_BLOB)["region"] == "us-east-1"
        with pytest.raises(ConnectorAuthError):
            bedrock_usage.parse_credential(json.dumps({**CRED, "secret_access_key": ""}))
        with pytest.raises(ConnectorAuthError):
            bedrock_usage.parse_credential(json.dumps({**CRED, "region": "not a region"}))

    def test_02_model_id_normalization(self) -> None:
        n = bedrock_usage.normalize_model_id
        assert n("us.anthropic.claude-sonnet-5-v1:0") == "anthropic.claude-sonnet-5"
        assert n("anthropic.claude-haiku-4-5-v2:1") == "anthropic.claude-haiku-4-5"
        assert (
            n("arn:aws:bedrock:us-east-1:123:inference-profile/eu.anthropic.claude-opus-4-8-v1:0")
            == "anthropic.claude-opus-4-8"
        )
        assert n("amazon.nova-pro-v1:0") == "amazon.nova-pro"

    def test_03_signature_is_deterministic_and_secret_sensitive(self) -> None:
        now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
        h1 = bedrock_usage._sign(dict(CRED), b"{}", "T.Action", now)
        h2 = bedrock_usage._sign(dict(CRED), b"{}", "T.Action", now)
        assert h1 == h2  # deterministic for fixed inputs
        other = bedrock_usage._sign(
            {**CRED, "secret_access_key": "different"}, b"{}", "T.Action", now
        )
        assert h1["Authorization"] != other["Authorization"]
        assert CRED["secret_access_key"] not in str(h1)  # secret never in headers
        assert h1["X-Amz-Date"] == "20260723T120000Z"


class TestFetch:
    def test_04_composition_mirrors_anthropic(self) -> None:
        http = FakeCloudWatch()
        buckets, pages = bedrock_usage.fetch_usage(
            CRED_BLOB, date(2026, 7, 20), date(2026, 7, 21), http
        )
        assert pages >= 2  # ListMetrics + >=1 GetMetricData
        by_key = {(b["day"].isoformat(), b["model"]): b for b in buckets}
        sonnet = by_key[("2026-07-20", "anthropic.claude-sonnet-5")]
        # prompt = input + cache_read + cache_write; cached = cache_read
        assert sonnet["prompt_tokens"] == 40000 + 50000 + 10000
        assert sonnet["cached_tokens"] == 50000
        assert (sonnet["calls"], sonnet["completion_tokens"]) == (120, 2000)
        haiku = by_key[("2026-07-20", "anthropic.claude-haiku-4-5")]
        assert haiku["prompt_tokens"] == 1024 + 1024  # no cache-write series
        # FR-22: counts only, exact key set
        assert all(
            set(b)
            == {"day", "model", "calls", "prompt_tokens", "completion_tokens", "cached_tokens"}
            for b in buckets
        )
        # every call carried a signed target
        assert all("Authorization" in c["headers"] for c in http.calls)

    def test_05_auth_refusals_typed_and_worded(self) -> None:
        bad = FakeCloudWatch(error_type="InvalidClientTokenId", error_status=400)
        verdict = validate.validate_key("bedrock", CRED_BLOB, bad)
        assert verdict.status == validate.BAD_KEY and "Access key ID" in verdict.detail
        denied = FakeCloudWatch(error_type="AccessDeniedException", error_status=400)
        verdict = validate.validate_key("bedrock", CRED_BLOB, denied)
        assert verdict.status == validate.NO_SCOPE
        assert "CloudWatchReadOnlyAccess" in verdict.detail
        assert not verdict.can_save


class TestRegistryPull:
    def test_06_run_pull_upserts_bedrock_buckets(
        self, session: Session, bare_settings: Settings
    ) -> None:
        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        src = Source(
            user_id=user.id,
            provider="bedrock",
            label="bedrock usage",
            credentials_encrypted=encrypt_credential(bare_settings.secret_key, CRED_BLOB),
        )
        session.add(src)
        session.commit()
        stats = run_pull(session, bare_settings, src, FakeCloudWatch())
        session.commit()
        assert stats.upserted == 3  # 2 sonnet days + 1 haiku day
        rows = session.execute(select(SourceUsage)).scalars().all()
        assert {r.model for r in rows} == {
            "anthropic.claude-sonnet-5",
            "anthropic.claude-haiku-4-5",
        }


class TestCacheVisibilityHonesty:
    def test_07_d2_runs_on_bedrock(self) -> None:
        """Bedrock EXPOSES cache counts — the cache detector must run, and
        coverage must say active (the mirror of Azure's blindness)."""
        assert "d2_missing_cache" in active_detectors("bedrock")
        rows = {str(r["detector"]): r for r in coverage_rows("bedrock")}
        assert rows["d2_missing_cache"]["status"] == "active"


class TestWizardJourney:
    def test_08_wizard_reachable_with_three_fields(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "Connect AWS Bedrock" in client.get("/sources", headers=HDR).text
        page = client.get("/sources/connect/bedrock", headers=HDR)
        assert page.status_code == 200
        for field in ("access_key_id", "secret_access_key", "region"):
            assert f'name="{field}"' in page.text
        assert "CloudWatchReadOnlyAccess" in page.text
        assert "listed, never guessed" in page.text  # unpriced truth BEFORE connect

    def test_09_validate_packs_three_fields_and_saves(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tokenops_cost_auditor.web import routes_sources

        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        monkeypatch.setattr(
            routes_sources.validate,
            "validate_key",
            lambda *a, **k: validate.VERDICTS[validate.UNREACHABLE],
        )
        resp = client.post("/sources/connect/bedrock/validate", data=CRED, headers=HDR)
        assert resp.status_code == 200
        with app.state.session_factory() as s:
            from tokenops_cost_auditor.services.connectors.crypto import decrypt_credential

            src = s.execute(select(Source).where(Source.provider == "bedrock")).scalar_one()
            assert (
                json.loads(
                    decrypt_credential(app.state.settings.secret_key, src.credentials_encrypted)
                )
                == CRED
            )

    def test_10_bad_region_refused_with_plain_words(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        resp = client.post(
            "/sources/connect/bedrock/validate",
            data={**CRED, "region": "USEast"},
            headers=HDR,
        )
        assert resp.status_code == 400
        assert "us-east-1" in resp.json()["detail"]  # the fix shown, not just "invalid"
