"""D6 runner + report tests — T-REP-01, T-REP-03, T-REP-08 (JSON), T-LIF-04,
T-NFR-11, L2 integration incl. real-Postgres path (docs/05 §1/§3)."""

import json
import shutil
import typing
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, CallAggregate, FindingRow, User
from tokenops_cost_auditor.services.ingest import load
from tokenops_cost_auditor.services.pricing.coster import apply, total_spend
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json, report_to_dict
from tokenops_cost_auditor.services.runner import AuditRunner, aggregate

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = PricingTable.load()

TEXT_MARKERS = ("CACHE-ME", "RETRY-ME", "D1-UNIQUE", "D3-rag", "D6-REREAD", "D5-UNIQUE")


def seed_audit(app: FastAPI, fixture: str, email: str = "runner@example.com") -> str:
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email)
            session.add(user)
            session.flush()
        audit = Audit(user_id=user.id, status="queued")
        session.add(audit)
        session.flush()
        upload_dir = Path(app.state.settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"original{Path(fixture).suffix}"
        shutil.copyfile(FIXTURES / fixture, dest)
        audit.upload_path = str(dest)
        session.commit()
        return audit.id


class TestRunnerEndToEnd:
    def test_waste_pack_full_pipeline(self, app: FastAPI, settings) -> None:
        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl")
        runner: AuditRunner = app.state.runner
        runner.run(audit_id)

        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None and audit.status == "done"
            assert audit.report_ready_at is not None  # NFR-11: set, UTC clock
            assert audit.provider_mix == "anthropic"
            assert audit.row_count == 147
            findings = list(
                session.scalars(select(FindingRow).where(FindingRow.audit_id == audit_id))
            )
            aggregates = list(
                session.scalars(select(CallAggregate).where(CallAggregate.audit_id == audit_id))
            )
        # anthropic file alone carries the D1/D2/D3/D6 blocks (D4/D5 are openai-shaped)
        assert {f.detector for f in findings} == {
            "d1_oversized_model",
            "d2_missing_cache",
            "d3_prompt_bloat",
            "d6_chatty_loop",
        }
        for f in findings:
            assert len(f.evidence_sample) <= 20
        assert aggregates, "call_aggregates persisted"
        # T-LIF-04: aggregates carry counts only — no text anywhere
        for row in aggregates:
            for value in (row.model, str(row.day)):
                for marker in TEXT_MARKERS:
                    assert marker not in value
        report_path = Path(settings.report_dir) / audit_id / "report.json"
        payload = report_path.read_text()
        for marker in TEXT_MARKERS:  # FR-22 at artifact level
            assert marker not in payload

    def test_rerun_is_idempotent(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl", email="rerun@example.com")
        runner: AuditRunner = app.state.runner
        runner.run(audit_id)
        runner.run(audit_id)  # admin re-run (FR-19): replaces derived rows
        with app.state.session_factory() as session:
            findings = list(
                session.scalars(select(FindingRow).where(FindingRow.audit_id == audit_id))
            )
            ids = [f.finding_id for f in findings]
        assert len(ids) == len(set(ids)), "re-run must not duplicate findings"


class TestTREP01ModelNumbersEqualEngineNumbers:
    def test_report_matches_engine(self, app: FastAPI, settings) -> None:
        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl", email="rep@example.com")
        app.state.runner.run(audit_id)
        report = json.loads((Path(settings.report_dir) / audit_id / "report.json").read_text())
        # recompute engine numbers independently of the report layer
        frame, _ = load(FIXTURES / "waste_pack_anthropic.jsonl")
        priced, unpriced = apply(TABLE, frame)
        assert report["summary"]["total_spend_usd"] == total_spend(priced)
        assert report["summary"]["observed_days"] == 3
        assert report["summary"]["monthly_spend_usd"] == total_spend(priced) * 10
        assert report["summary"]["monthly_savings_usd"] == pytest.approx(
            sum(f["monthly_cost_impact_usd"] for f in report["findings"]), abs=1e-15
        )
        assert report["summary"]["monthly_optimized_usd"] == pytest.approx(
            report["summary"]["monthly_spend_usd"] - report["summary"]["monthly_savings_usd"],
            abs=1e-15,
        )
        assert report["pricing"]["unpriced_models"] == unpriced
        # findings ranked by monthly $ impact (FR-14)
        impacts = [f["monthly_cost_impact_usd"] for f in report["findings"]]
        assert impacts == sorted(impacts, reverse=True)

    def test_render_is_deterministic(self) -> None:
        frame, _ = load(FIXTURES / "waste_pack_anthropic.jsonl")
        priced, unpriced = apply(TABLE, frame)
        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.services.rules.base import DetectorContext
        from tokenops_cost_auditor.services.rules.findings import observed_days
        from tokenops_cost_auditor.services.rules.registry import run_all

        ctx = DetectorContext(Settings(_env_file=None), TABLE, observed_days(priced))
        findings = run_all(priced, ctx)
        one = report_to_dict(
            ReportModel.build("a1", priced, findings, unpriced, TABLE, generated_at=None)
        )
        two = report_to_dict(
            ReportModel.build("a1", priced, findings, unpriced, TABLE, generated_at=None)
        )
        assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)


class TestTREP03JsonSchema:
    REQUIRED: typing.ClassVar[dict[str, type]] = {
        "schema_version": int,
        "audit_id": str,
        "pricing": dict,
        "summary": dict,
        "spend_by_model": list,
        "spend_by_day": list,
        "findings": list,
        "methodology": str,
        "data_handling": str,
    }

    def test_schema_shape(self, app: FastAPI, settings) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl", email="schema@example.com")
        app.state.runner.run(audit_id)
        report = json.loads((Path(settings.report_dir) / audit_id / "report.json").read_text())
        for key, typ in self.REQUIRED.items():
            assert isinstance(report.get(key), typ), key
        for k in (
            "total_spend_usd",
            "monthly_spend_usd",
            "monthly_savings_usd",
            "monthly_optimized_usd",
            "savings_pct",
            "observed_days",
            "row_count",
        ):
            assert k in report["summary"]
        for f in report["findings"]:
            assert set(f) == {
                "id",
                "detector",
                "severity",
                "confidence",
                "monthly_cost_impact_usd",
                "fix_text",
                "evidence",
                "detail",  # R-D6-AGG: per-run/cluster breakdown (null when not aggregated)
            }


class TestTREP08PricingProvenance:
    def test_json_carries_pricing_version_and_unpriced(self, tmp_path: Path) -> None:
        frame, _ = load(FIXTURES / "openai_small.jsonl")
        priced, unpriced = apply(TABLE, frame)
        report = ReportModel.build("a2", priced, [], unpriced, TABLE)
        payload = json.loads(render_json(report, tmp_path / "r.json").read_text())
        assert payload["pricing"]["version"] == TABLE.version  # FR-28
        assert payload["pricing"]["last_verified"] == "2026-07-17"
        assert payload["pricing"]["unpriced_model_count"] == 0
        # unknown model shows up in the list, audit continues
        weird = frame.copy()
        weird.loc[weird.index[:3], "model"] = "mystery-9000"
        priced2, unpriced2 = apply(TABLE, weird)
        report2 = ReportModel.build("a3", priced2, [], unpriced2, TABLE)
        payload2 = report_to_dict(report2)
        assert payload2["pricing"]["unpriced_models"] == ["openai/mystery-9000"]
        assert payload2["pricing"]["unpriced_model_count"] == 1


class TestTNFR11Utc:
    def test_report_days_are_utc_dates_and_aggregate_days_match(self) -> None:
        frame, _ = load(FIXTURES / "waste_pack_anthropic.jsonl")
        priced, _ = apply(TABLE, frame)
        rows = aggregate(priced)
        days = {str(r["day"]) for r in rows}
        assert days == {"2026-06-10", "2026-06-11", "2026-06-12"}  # UTC day keys
        assert all(isinstance(r["prompt_tokens"], int) for r in rows)

    def test_frame_timestamps_are_utc(self) -> None:
        frame, _ = load(FIXTURES / "openai_small.jsonl")
        assert str(frame["ts"].dt.tz) == "UTC"


class TestPostgresIntegration:
    """L2 vs real Postgres (CI service). Skipped locally without DATABASE_URL."""

    def test_migrations_then_full_runner(
        self, ci_database_url: str, tmp_path: Path, monkeypatch
    ) -> None:
        from alembic import command
        from alembic.config import Config

        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.main import create_app

        monkeypatch.setenv("DATABASE_URL", ci_database_url)
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", ci_database_url)
        command.upgrade(cfg, "head")

        settings = Settings(
            app_env="test",
            database_url=ci_database_url,
            upload_dir=tmp_path / "uploads",
            report_dir=tmp_path / "reports",
            _env_file=None,
        )
        app = create_app(settings)
        try:
            audit_id = seed_audit(app, "openai_small.jsonl", email="pg@example.com")
            app.state.runner.run(audit_id)
            with app.state.session_factory() as session:
                audit = session.get(Audit, audit_id)
                assert audit is not None and audit.status == "done"
                assert audit.total_spend_usd is not None and audit.total_spend_usd > 0
        finally:
            app.state.engine.dispose()


def test_aggregate_empty_frame() -> None:
    frame, _ = load(FIXTURES / "openai_small.jsonl")
    priced, _ = apply(TABLE, frame)
    assert aggregate(priced.iloc[0:0]) == []
    assert isinstance(priced, pd.DataFrame)
