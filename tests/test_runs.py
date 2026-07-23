"""WP-PIPELINE-UI tests — the runs observatory.

Per-stage StageEvents from both pipelines (recorded, never estimated),
the pull ledger (every pull including failures), alert-check rows
("checked, nothing crossed" is evidence), and the /runs page journey:
kit ribbon, honest zeros, FR-31 purged rows, in-flight self-poll.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from test_connectors import OPENAI_PAGE, FakeHTTP, make_source
from test_runner import seed_audit
from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    AlertCheck,
    AlertRule,
    Audit,
    Base,
    PullEvent,
    SourceUsage,
    StageEvent,
    User,
)
from tokenops_cost_auditor.services.alerts import dispatch
from tokenops_cost_auditor.services.alerts.rules import SPEND_SPIKE, WASTE_ABOVE
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError
from tokenops_cost_auditor.services.connectors.pull import record_pull_failure, run_pull
from tokenops_cost_auditor.services.connectors.source_audit import (
    ACTIVE_ON_AGGREGATE,
    run_source_audit,
)
from tokenops_cost_auditor.services.lifecycle.purge import purge_one
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.rules.registry import DETECTORS

EMAIL = "runner@example.com"
HDR = {"X-User-Email": EMAIL}


@pytest.fixture()
def bare_settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/r.db", _env_file=None)


@pytest.fixture()
def session(bare_settings: Settings) -> Session:
    engine = create_engine(bare_settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def stage_names(session: Session, audit_id: str) -> list[str]:
    return list(
        session.execute(
            select(StageEvent.stage)
            .where(StageEvent.audit_id == audit_id)
            .order_by(StageEvent.started_at)
        ).scalars()
    )


class TestRunnerStageEvents:
    def test_01_four_stages_recorded_in_order(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl")
        app.state.runner.run(audit_id)
        with app.state.session_factory() as session:
            events = (
                session.execute(
                    select(StageEvent)
                    .where(StageEvent.audit_id == audit_id)
                    .order_by(StageEvent.started_at)
                )
                .scalars()
                .all()
            )
            assert [e.stage for e in events] == ["ingest", "price", "detect", "report"]
            for e in events:
                assert e.finished_at is not None and e.finished_at >= e.started_at
            ingest, price, detect, report = events
            assert ingest.detail["rows"] >= 1 and "rejected" in ingest.detail
            assert "priced_rows" in price.detail and "unpriced_models" in price.detail
            # Honest zeros: EVERY registered detector appears, found or not.
            assert set(detect.detail["detectors"]) == {d.name for d in DETECTORS}
            assert report.detail["artifacts"] == ["json", "html", "pdf"]

    def test_02_rerun_replaces_stage_events(self, app: FastAPI) -> None:
        """FR-19: re-runs replace derived rows — stage events included."""
        audit_id = seed_audit(app, "openai_small.jsonl")
        app.state.runner.run(audit_id)
        app.state.runner.run(audit_id)
        with app.state.session_factory() as session:
            assert len(stage_names(session, audit_id)) == 4


class TestSourceAuditStageEvents:
    def test_03_stages_in_execution_order(self, session: Session, bare_settings: Settings) -> None:
        src = make_source(session, bare_settings, "openai")
        today = datetime.now(UTC).date()
        session.add(
            SourceUsage(
                source_id=src.id,
                day=today - timedelta(days=1),
                model="gpt-4o-mini",
                calls=100,
                prompt_tokens=50_000,
                completion_tokens=5_000,
                cached_tokens=0,
            )
        )
        session.commit()
        audit_id = run_source_audit(session, bare_settings, PricingTable.load(), src)
        session.commit()
        # Bucket audits detect BEFORE pricing — the ledger tells it as it ran.
        assert stage_names(session, audit_id) == ["ingest", "detect", "price", "report"]
        detect = session.execute(
            select(StageEvent).where(StageEvent.audit_id == audit_id, StageEvent.stage == "detect")
        ).scalar_one()
        assert set(detect.detail["detectors"]) == set(ACTIVE_ON_AGGREGATE)

    def test_03b_redriven_precreated_row_replaces_stage_events(
        self, session: Session, bare_settings: Settings
    ) -> None:
        """cold-review f.1: a pre-created row re-driven after a partial
        failure must replace its stage events, never accumulate them."""
        src = make_source(session, bare_settings, "openai")
        session.add(
            SourceUsage(
                source_id=src.id,
                day=datetime.now(UTC).date() - timedelta(days=1),
                model="gpt-4o-mini",
                calls=10,
                prompt_tokens=5_000,
                completion_tokens=500,
                cached_tokens=0,
            )
        )
        pre = Audit(user_id=src.user_id, status="queued")
        session.add(pre)
        session.commit()
        table = PricingTable.load()
        run_source_audit(session, bare_settings, table, src, audit=pre)
        session.commit()
        run_source_audit(session, bare_settings, table, src, audit=pre)
        session.commit()
        assert len(stage_names(session, pre.id)) == 4


class TestPullLedger:
    def test_04_success_row_rides_the_pull(self, session: Session, bare_settings: Settings) -> None:
        src = make_source(session, bare_settings, "openai")
        stats = run_pull(session, bare_settings, src, FakeHTTP(OPENAI_PAGE))
        session.commit()
        ev = session.execute(select(PullEvent)).scalar_one()
        assert ev.ok is True and ev.source_id == src.id
        assert (ev.buckets_in, ev.upserted, ev.updated) == (
            stats.buckets_in,
            stats.upserted,
            stats.updated_existing,
        )

    def test_05_failure_rows_are_user_safe(self, session: Session, bare_settings: Settings) -> None:
        src = make_source(session, bare_settings, "openai")
        record_pull_failure(session, src.id, ConnectorAuthError("anything", status=401))
        record_pull_failure(session, src.id, RuntimeError("Traceback: sk-secret leaked"))
        events = session.execute(select(PullEvent).order_by(PullEvent.id)).scalars().all()
        assert [e.ok for e in events] == [False, False]
        assert events[0].error == "provider rejected the stored key"
        assert events[1].error == "pull failed — provider or network error"
        assert "sk-secret" not in (events[1].error or "")


class TestAlertChecks:
    def test_06_silence_is_recorded(self, session: Session, bare_settings: Settings) -> None:
        user = User(email="quiet@example.com")
        session.add(user)
        session.flush()
        session.add(AlertRule(user_id=user.id, rule=SPEND_SPIKE, threshold=30.0, enabled=True))
        session.add(AlertRule(user_id=user.id, rule=WASTE_ABOVE, threshold=1.0, enabled=False))
        session.commit()
        assert dispatch.run_for_user(session, bare_settings, object(), user) == []
        checks = session.execute(select(AlertCheck)).scalars().all()
        # One row per ENABLED rule; the disabled rule is not "checked".
        assert [(c.rule, c.crossed, c.note) for c in checks] == [
            (SPEND_SPIKE, False, "checked — nothing crossed")
        ]

    def test_07_firing_is_stamped_crossed(self, session: Session, bare_settings: Settings) -> None:
        user = User(email="loud@example.com")
        session.add(user)
        session.flush()
        session.add(AlertRule(user_id=user.id, rule=SPEND_SPIKE, threshold=30.0, enabled=True))
        t0 = datetime.now(UTC) - timedelta(days=14)
        for when, spend in ((t0, 1000.0), (t0 + timedelta(days=7), 1400.0)):
            session.add(
                Audit(
                    user_id=user.id,
                    status="done",
                    created_at=when,
                    report_ready_at=when,
                    observed_days=7,
                    row_count=100,
                    total_spend_usd=spend,
                    savings_pct=5.0,
                )
            )
        session.commit()
        fired = dispatch.run_for_user(session, bare_settings, object(), user)
        assert [f.rule for f in fired] == [SPEND_SPIKE]
        check = session.execute(select(AlertCheck)).scalar_one()
        assert check.crossed is True and check.note == "fired — emailed"


class TestRunsPage:
    def test_08_run_renders_with_kit_ribbon_and_honest_zeros(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl")
        app.state.runner.run(audit_id)
        page = TestClient(app).get("/runs", headers=HDR)
        assert page.status_code == 200
        assert 'class="ribbon ribbon-4"' in page.text  # ONE ribbon grammar (F4)
        for label in ("Ingest", "Price", "Detect", "Report"):
            assert label in page.text
        assert "file upload" in page.text  # trigger mapping for uploads
        assert "an honest zero, not a skip" in page.text  # some detector found nothing
        squashed = re.sub(r"\s+", " ", page.text)
        assert "every one this account ever made" in squashed  # FR-31 line

    def test_09_purged_run_stays_listed_without_download(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl")
        app.state.runner.run(audit_id)
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            assert purge_one(session, audit) is True
            session.commit()
        page = TestClient(app).get("/runs", headers=HDR)
        assert "raw logs purged (kept: counts, findings, report)" in page.text
        assert f"/audits/{audit_id}/row-errors" not in page.text
        # Stage timings survive the purge — they are counts, not raw logs.
        with app.state.session_factory() as session:
            assert len(stage_names(session, audit_id)) == 4

    def test_10_pre_stage_history_says_so(self, app: FastAPI) -> None:
        """Runs from before this release have no stage rows — the drawer
        states that instead of pretending (no invented timings, ever)."""
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            session.add(Audit(user_id=user.id, status="done", row_count=10, total_spend_usd=1.0))
            session.commit()
        page = TestClient(app).get("/runs", headers=HDR)
        assert "predates per-stage timing" in page.text

    def test_11_in_flight_run_polls_and_links_to_theater(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl")
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            audit.status = "processing"
            session.commit()
        client = TestClient(app)
        page = client.get("/runs", headers=HDR)
        assert 'hx-get="/runs/partial"' in page.text  # self-poll while in flight
        assert f"/audits/{audit_id}/progress" in page.text  # the live theater
        partial = client.get("/runs/partial", headers=HDR)
        assert partial.status_code == 200 and 'id="runs-ledger"' in partial.text

    def test_12_idle_page_never_polls(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl")
        app.state.runner.run(audit_id)
        page = TestClient(app).get("/runs", headers=HDR)
        assert 'hx-get="/runs/partial"' not in page.text

    def test_14_drawer_total_reconciles_with_dashboard_headline(self, app: FastAPI) -> None:
        """system-tester f.6: per-detector lines round independently, so their
        naive sum can drift a cent from the dashboard's "identified" headline.
        The drawer therefore states its own total summed BEFORE rounding — and
        for a fresh audit (no feedback) that figure must equal the dashboard's
        to the character."""
        from tokenops_cost_auditor.persistence.models import FindingRow

        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        with app.state.session_factory() as session:
            total = sum(
                float(r.monthly_impact_usd)
                for r in session.execute(
                    select(FindingRow).where(FindingRow.audit_id == audit_id)
                ).scalars()
            )
        assert total > 0
        figure = f"${total:,.2f}/mo"
        client = TestClient(app)
        dash = re.sub(r"\s+", " ", client.get("/dashboard", headers=HDR).text)
        runs = re.sub(r"\s+", " ", client.get("/runs", headers=HDR).text)
        assert f"{figure} identified — latest audit" in dash
        assert f"{figure} across" in runs  # the drawer's summed-before-rounding total

    def test_13_pull_and_check_ledgers_render(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # creates the account
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            src = make_source(session, app.state.settings, "openai")
            src.user_id = user.id
            session.add(PullEvent(source_id=src.id, ok=True, buckets_in=31, upserted=2, updated=29))
            session.add(
                PullEvent(source_id=src.id, ok=False, error="provider rejected the stored key")
            )
            session.add(
                AlertCheck(
                    user_id=user.id,
                    rule=SPEND_SPIKE,
                    crossed=False,
                    note="checked — nothing crossed",
                )
            )
            session.commit()
        page = client.get("/runs", headers=HDR)
        assert "31 in · 2 new · 29 updated" in page.text
        assert "provider rejected the stored key" in page.text  # failures shown
        assert "checked — nothing crossed" in page.text
