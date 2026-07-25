"""T-CON-04 + source-audit wiring (PLAN-V15 WP-1): tier labeling, honest
coverage rows (R-Q1 law), spend/persistence semantics for T2 audits."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Audit,
    Base,
    CallAggregate,
    FindingRow,
    Source,
    SourceUsage,
    User,
)
from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit
from tokenops_cost_auditor.services.pricing.table import PricingTable

FIXTURE = json.loads(Path("tests/fixtures/aggregate_usage.json").read_text(encoding="utf-8"))


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key="k" * 64,
        database_url=f"sqlite:///{tmp_path}/sa.db",
        report_dir=tmp_path / "reports",
        _env_file=None,
    )


@pytest.fixture()
def session(settings: Settings) -> Session:
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture()
def source(session: Session, settings: Settings) -> Source:
    user = User(email="owner@example.com")
    session.add(user)
    session.flush()
    src = Source(user_id=user.id, provider="anthropic", label="org", credentials_encrypted="x")
    session.add(src)
    session.flush()
    # Re-date fixture buckets into the audit window (relative to today)
    today = datetime.now(UTC).date()
    fixture_days = sorted({b["day"] for b in FIXTURE["buckets"]})
    day_map = {d: today - timedelta(days=len(fixture_days) - i) for i, d in enumerate(fixture_days)}
    for b in FIXTURE["buckets"]:
        session.add(
            SourceUsage(
                source_id=src.id,
                day=day_map[b["day"]],
                model=b["model"],
                calls=b["calls"],
                prompt_tokens=b["prompt_tokens"],
                completion_tokens=b["completion_tokens"],
                cached_tokens=b["cached_tokens"],
                provenance={"pull": "test"},
            )
        )
    session.commit()
    return src


class TestLiveAuditLifecycle:
    """R-LIVE-AUDIT: a pre-created 'queued' row is finalized in place, so the
    live theater has a stable id to poll from queued → processing → done."""

    def test_prewatched_row_is_finalized_in_place(
        self, session: Session, settings: Settings, source: Source
    ) -> None:
        # the connect kickoff creates this synchronously, then hands the id to
        # the browser and processes in a thread
        pre = Audit(user_id=source.user_id, status="queued", paid_via="subscription")
        session.add(pre)
        session.commit()
        pre_id = pre.id

        returned = run_source_audit(session, settings, PricingTable.load(), source, audit=pre)
        session.commit()

        # SAME row the browser is polling — not a second audit
        assert returned == pre_id
        assert session.query(Audit).count() == 1
        finalized = session.get(Audit, pre_id)
        assert finalized.status == "done"
        assert finalized.row_count == 750  # fully populated as a normal audit
        report = settings.report_dir / pre_id / "report.json"
        assert report.exists()

    def test_default_still_creates_its_own_row(
        self, session: Session, settings: Settings, source: Source
    ) -> None:
        # scheduled / re-audit callers pass no row and get a fresh done audit
        audit_id = run_source_audit(session, settings, PricingTable.load(), source)
        session.commit()
        assert session.get(Audit, audit_id).status == "done"

    def test_orphaned_queued_row_marked_failed_when_source_vanishes(
        self, settings: Settings
    ) -> None:
        # cold-review f.2: if the source is gone before the worker runs, the
        # pre-created queued row must reach a terminal state, not poll forever.
        from sqlalchemy.orm import sessionmaker

        from tokenops_cost_auditor.web.routes_sources import _process_first_pull

        engine = create_engine(settings.database_url)
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine)
        with factory() as s:
            user = User(email="orphan@example.com")
            s.add(user)
            s.flush()
            row = Audit(user_id=user.id, status="queued", paid_via="subscription")
            s.add(row)
            s.commit()
            audit_id = row.id

        _process_first_pull(
            factory, settings, PricingTable.load(), "no-such-source", audit_id, None
        )

        with factory() as s:
            reloaded = s.get(Audit, audit_id)
            assert reloaded.status == "failed"
            assert reloaded.error


class TestSourceAudit:
    def test_01_tier_and_coverage_labeling(
        self, session: Session, settings: Settings, source: Source
    ) -> None:
        audit_id = run_source_audit(session, settings, PricingTable.load(), source)
        session.commit()
        report = json.loads(
            (settings.report_dir / audit_id / "report.json").read_text(encoding="utf-8")
        )
        assert report["tier"] == "account"
        cov = {c["detector"]: c for c in report["coverage"]}
        assert len(cov) == 9
        for d in ("d1_oversized_model", "d2_missing_cache", "d3_prompt_bloat"):
            assert cov[d]["status"] == "active"
        for d in (
            "d4_retry_storm",
            "d5_unbounded_max_tokens",
            "d6_chatty_loop",
            "d8_spend_concentration",
            "d9_ineffective_cache",
            "d10_spend_anomaly",
        ):
            assert cov[d]["status"] == "requires_per_request_logs"
            assert "per-request logs" in cov[d]["note"]
            # R-Q1 law: an inactive row NEVER carries a savings number
            assert not any("usd" in k or "savings" in k for k in cov[d])
        # no equiv-spend framing: T2 pulls are metered API billing
        assert report["summary"]["equiv_spend"] is False

    def test_02_spend_and_calls_semantics(
        self, session: Session, settings: Settings, source: Source
    ) -> None:
        audit_id = run_source_audit(session, settings, PricingTable.load(), source)
        session.commit()
        report = json.loads(
            (settings.report_dir / audit_id / "report.json").read_text(encoding="utf-8")
        )
        # row_count = SUM of provider-reported calls (750), never bucket count (8)
        assert report["summary"]["row_count"] == 750
        # 4 distinct days re-dated into the window
        assert report["summary"]["observed_days"] == 4
        # as-billed window spend, hand-derived: 7.425 + 6.8 + 5.45 = 19.675
        assert report["summary"]["total_spend_usd"] == pytest.approx(19.675)
        # headline == min(sum of findings, monthly spend); 5 golden findings
        # rescaled from x3 (10 days) to x7.5 (4 days): 24.831/3*7.5 = 62.0775
        assert len(report["findings"]) == 5
        assert report["summary"]["monthly_savings_usd"] == pytest.approx(62.0775)

    def test_03_persistence_mirrors_upload_shape(
        self, session: Session, settings: Settings, source: Source
    ) -> None:
        audit_id = run_source_audit(session, settings, PricingTable.load(), source)
        session.commit()
        audit = session.get(Audit, audit_id)
        assert audit is not None and audit.status == "done"
        assert audit.paid_via == "subscription"
        assert audit.row_count == 750
        assert (
            session.execute(select(FindingRow).where(FindingRow.audit_id == audit_id))
            .scalars()
            .all()
        )
        aggs = (
            session.execute(select(CallAggregate).where(CallAggregate.audit_id == audit_id))
            .scalars()
            .all()
        )
        assert len(aggs) == 8  # one per bucket
        assert source.last_audit_at is not None
