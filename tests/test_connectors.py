"""T-CON-01..06 (PLAN-V15 WP-1): connector parsing, pull upsert idempotence,
revoke semantics, FR-22 counts-only at the T2 door."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Base, Source, SourceUsage, User
from tokenops_cost_auditor.services.connectors import anthropic_usage, openai_usage
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.pull import run_pull

OPENAI_PAGE = {
    "object": "page",
    "data": [
        {
            "object": "bucket",
            "start_time": int(datetime(2026, 7, 18, tzinfo=UTC).timestamp()),
            "end_time": int(datetime(2026, 7, 19, tzinfo=UTC).timestamp()),
            "results": [
                {
                    "object": "organization.usage.completions.result",
                    "model": "gpt-5.6-sol",
                    "num_model_requests": 42,
                    "input_tokens": 100000,
                    "input_cached_tokens": 40000,
                    "output_tokens": 9000,
                },
                {
                    "object": "organization.usage.completions.result",
                    "model": "gpt-5.5-luna",
                    "num_model_requests": 10,
                    "input_tokens": 5000,
                    "input_cached_tokens": 0,
                    "output_tokens": 800,
                },
            ],
        }
    ],
    "has_more": False,
    "next_page": None,
}

ANTHROPIC_PAGE = {
    "data": [
        {
            "starting_at": "2026-07-18T00:00:00Z",
            "ending_at": "2026-07-19T00:00:00Z",
            "results": [
                {
                    "model": "claude-sonnet-5",
                    "num_requests": 7,
                    "uncached_input_tokens": 10000,
                    "cache_read_input_tokens": 30000,
                    "cache_creation": {"ephemeral_5m_input_tokens": 2000},
                    "output_tokens": 1500,
                }
            ],
        }
    ],
    "has_more": False,
    "next_page": None,
}


class FakeHTTP:
    """Minimal stand-in for httpx.Client: returns canned pages, no network."""

    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, headers: dict) -> FakeHTTP:
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/c.db", _env_file=None)


@pytest.fixture()
def session(settings: Settings) -> Session:
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def make_source(session: Session, settings: Settings, provider: str) -> Source:
    user = User(email="owner@example.com")
    session.add(user)
    session.flush()
    src = Source(
        user_id=user.id,
        provider=provider,
        label=f"{provider} org",
        credentials_encrypted=encrypt_credential(settings.secret_key, "sk-admin-secret-1"),
    )
    session.add(src)
    session.commit()
    return src


class TestParsing:
    def test_01_openai_page_to_buckets(self) -> None:
        rows = openai_usage.parse_page(OPENAI_PAGE)
        assert len(rows) == 2
        sol = next(r for r in rows if r["model"] == "gpt-5.6-sol")
        assert sol == {
            "day": date(2026, 7, 18),
            "model": "gpt-5.6-sol",
            "calls": 42,
            "prompt_tokens": 100000,
            "completion_tokens": 9000,
            "cached_tokens": 40000,
        }

    def test_02_anthropic_page_to_buckets(self) -> None:
        rows = anthropic_usage.parse_page(ANTHROPIC_PAGE)
        assert rows == [
            {
                "day": date(2026, 7, 18),
                "model": "claude-sonnet-5",
                "calls": 7,
                # uncached 10k + cache_read 30k + cache_creation 2k
                "prompt_tokens": 42000,
                "completion_tokens": 1500,
                "cached_tokens": 30000,
            }
        ]

    def test_06_fr22_no_text_fields_anywhere(self) -> None:
        for rows in (
            openai_usage.parse_page(OPENAI_PAGE),
            anthropic_usage.parse_page(ANTHROPIC_PAGE),
        ):
            for row in rows:
                assert set(row) == {
                    "day",
                    "model",
                    "calls",
                    "prompt_tokens",
                    "completion_tokens",
                    "cached_tokens",
                }


class TestPull:
    def test_03_upsert_idempotent_with_stats(self, session: Session, settings: Settings) -> None:
        src = make_source(session, settings, "openai")
        stats1 = run_pull(session, settings, src, FakeHTTP(OPENAI_PAGE))
        session.commit()
        assert (stats1.buckets_in, stats1.upserted, stats1.updated_existing) == (2, 2, 0)
        assert "buckets_in=2" in stats1.summary()
        stats2 = run_pull(session, settings, src, FakeHTTP(OPENAI_PAGE))
        session.commit()
        assert (stats2.upserted, stats2.updated_existing) == (0, 2)
        rows = session.execute(select(SourceUsage)).scalars().all()
        assert len(rows) == 2  # never duplicated
        assert src.last_pull_at is not None
        assert rows[0].provenance["endpoint"].startswith("https://api.openai.com")

    def test_04_revoked_or_paused_source_never_pulled(
        self, session: Session, settings: Settings
    ) -> None:
        src = make_source(session, settings, "anthropic")
        src.status = "revoked"
        src.credentials_encrypted = None  # revoke deletes ciphertext
        session.commit()
        with pytest.raises(ValueError, match="not active"):
            run_pull(session, settings, src, FakeHTTP(ANTHROPIC_PAGE))
        src.status = "paused"
        src.credentials_encrypted = encrypt_credential(settings.secret_key, "sk-2")
        session.commit()
        with pytest.raises(ValueError, match="not active"):
            run_pull(session, settings, src, FakeHTTP(ANTHROPIC_PAGE))

    def test_05_backfill_window_on_first_pull(self, session: Session, settings: Settings) -> None:
        src = make_source(session, settings, "openai")
        fake = FakeHTTP(OPENAI_PAGE)
        run_pull(session, settings, src, fake)
        params = fake.calls[0]["params"]
        window_s = int(params["end_time"]) - int(params["start_time"])
        # 30-day backfill (accepted default Q2) + the end-exclusive day
        assert window_s == (settings.connect_backfill_days + 1) * 86400
        # key travels in the header and is never persisted anywhere
        assert fake.calls[0]["headers"]["Authorization"] == "Bearer sk-admin-secret-1"
        assert json.dumps({"p": params}, default=str).count("sk-admin") == 0
