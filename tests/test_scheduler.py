"""T-SCH-01..03 (PLAN-V15 WP-3a): due computation, idempotent tick,
per-source cadence and error isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from test_connectors import OPENAI_PAGE
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Base, Source, Subscription, User
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.schedule import due_audits, due_pulls, tick
from tokenops_cost_auditor.services.pricing.table import PricingTable

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key="k" * 64,
        database_url=f"sqlite:///{tmp_path}/sch.db",
        report_dir=tmp_path / "reports",
        _env_file=None,
    )


@pytest.fixture()
def session(settings: Settings) -> Session:
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def add_source(session: Session, settings: Settings, **kw: object) -> Source:
    user = session.query(User).first()
    if user is None:
        user = User(email="owner@example.com")
        session.add(user)
        session.flush()
        # A connected source implies a paid plan (Free has no connections,
        # R-Q5/Q6) — and scheduled audits are a Pro entitlement.
        session.add(Subscription(user_id=user.id, provider="stripe", plan="pro"))
        session.flush()
    src = Source(
        user_id=user.id,
        provider="openai",
        label="org",
        credentials_encrypted=encrypt_credential(settings.secret_key, "sk-1"),
    )
    for k, v in kw.items():
        setattr(src, k, v)
    session.add(src)
    session.commit()
    return src


class TestDueComputation:
    def test_01_due_rules(self, session: Session, settings: Settings) -> None:
        never_pulled = add_source(session, settings)
        fresh = add_source(session, settings, last_pull_at=NOW - timedelta(hours=2))
        stale = add_source(session, settings, last_pull_at=NOW - timedelta(days=2))
        revoked = add_source(session, settings, status="revoked", credentials_encrypted=None)
        paused = add_source(session, settings, status="paused")

        due = {s.id for s in due_pulls(session, NOW)}
        assert never_pulled.id in due and stale.id in due
        assert fresh.id not in due and revoked.id not in due and paused.id not in due

        # audits: only after a first pull landed data; weekly cadence
        assert due_audits(session, NOW) != []  # fresh+stale have pulls, no audit yet
        audited = {s.id for s in due_audits(session, NOW)}
        assert never_pulled.id not in audited  # no pull yet -> nothing to audit
        fresh.last_audit_at = NOW - timedelta(days=2)
        session.commit()
        assert fresh.id not in {s.id for s in due_audits(session, NOW)}
        fresh.last_audit_at = NOW - timedelta(days=8)
        session.commit()
        assert fresh.id in {s.id for s in due_audits(session, NOW)}


class TestTick:
    def test_02_tick_idempotent(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_source(session, settings)
        import tokenops_cost_auditor.services.connectors.pull as pull_mod

        monkeypatch.setattr(
            pull_mod,
            "_CLIENTS",
            {
                "openai": (
                    lambda key, s, e, c=None: (
                        __import__(
                            "tokenops_cost_auditor.services.connectors.openai_usage",
                            fromlist=["parse_page"],
                        ).parse_page(OPENAI_PAGE),
                        1,
                    ),
                    "https://api.openai.com/test",
                )
            },
        )
        table = PricingTable.load()
        stats1 = tick(session, settings, table, now=NOW)
        assert stats1["pulled"] == 1 and stats1["pull_errors"] == 0
        # audit ran too: pull stamped last_pull_at, source never audited
        assert stats1["audited"] == 1
        stats2 = tick(session, settings, table, now=NOW + timedelta(minutes=30))
        # second tick within the hour: nothing due — the idempotence posture
        assert stats2 == {"pulled": 0, "pull_errors": 0, "audited": 0, "audit_errors": 0}

    def test_03_error_isolation(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_source(session, settings)  # will fail (no fake client wired)
        ok = add_source(session, settings)
        import tokenops_cost_auditor.services.connectors.pull as pull_mod

        real_clients = dict(pull_mod._CLIENTS)
        calls = {"n": 0}

        def flaky_fetch(key: str, s: object, e: object, c: object = None) -> tuple[list, int]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("provider 500")
            from tokenops_cost_auditor.services.connectors.openai_usage import parse_page

            return parse_page(OPENAI_PAGE), 1

        real_clients["openai"] = (flaky_fetch, "https://api.openai.com/test")
        monkeypatch.setattr(pull_mod, "_CLIENTS", real_clients)
        stats = tick(session, settings, PricingTable.load(), now=NOW)
        # one source failed, the other still pulled and audited
        assert stats["pull_errors"] == 1 and stats["pulled"] == 1
        assert stats["audited"] == 1
        assert ok is not None

    def test_04_pull_ledger_failure_is_isolated(
        self, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Coverage debt §3 #9: if RECORDING a pull failure itself fails, tick still
        counts the error and never crashes — the nested best-effort handler that only
        the exact 'ledger write also throws' path exercises (schedule.py:107-109)."""
        import tokenops_cost_auditor.services.connectors.schedule as sch

        add_source(session, settings)  # a due, never-pulled source

        def boom_pull(*a: object, **k: object) -> None:
            raise RuntimeError("provider 500")

        def boom_ledger(*a: object, **k: object) -> None:
            raise RuntimeError("ledger write failed too")

        monkeypatch.setattr(sch, "run_pull", boom_pull)
        monkeypatch.setattr(sch, "record_pull_failure", boom_ledger)
        stats = tick(session, settings, PricingTable.load(), now=NOW)
        assert stats["pull_errors"] == 1  # counted, not crashed
        assert stats["pulled"] == 0
