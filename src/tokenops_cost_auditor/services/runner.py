"""AuditRunner — orchestrates the audit pipeline (docs/03-LLD.md §4).

Status flow: queued -> processing -> done|failed. NFR-13: a run waits for a free
slot while the number of processing audits is at MAX_CONCURRENT_AUDITS (audits
hold `queued`; the status API reports queue position). Re-runs are idempotent
(FR-19): previous findings/aggregates are replaced. Failure persists a USER-SAFE
message only (LLD §8); internals go to logs/error hook.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import Engine, delete

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.obs import errors as obs_errors
from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingRow,
    StageEvent,
    User,
)
from tokenops_cost_auditor.persistence.repo import make_session_factory, processing_count
from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.flywheel import benchmarks as flywheel_benchmarks
from tokenops_cost_auditor.services.ingest.base import IngestError
from tokenops_cost_auditor.services.ingest.validator import enforce, write_error_file
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.mail.base import MailPort
from tokenops_cost_auditor.services.pricing import coster
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.report.render_pdf import render_pdf, render_report_html
from tokenops_cost_auditor.services.report.signer import sign_report_url
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import Finding, observed_days
from tokenops_cost_auditor.services.rules.registry import DETECTORS, run_all

log = structlog.get_logger("tokenops_cost_auditor.runner")


def aggregate(priced: pd.DataFrame) -> list[dict[str, object]]:
    """call_aggregates rows: counts only (FR-22, T-LIF-04)."""
    out: list[dict[str, object]] = []
    if len(priced) == 0:
        return out
    grouped = priced.groupby([priced["ts"].dt.date, "model"], sort=True)
    for (day, model), group in grouped:
        costs = group["cost_usd"].dropna()
        out.append(
            {
                "day": day,
                "model": str(model),
                "calls": len(group),
                "prompt_tokens": int(group["prompt_tokens"].sum()),
                "completion_tokens": int(group["completion_tokens"].sum()),
                "cached_tokens": int(group["cached_tokens"].sum()),
                "cost_usd": float(costs.sum()) if len(costs) else None,
            }
        )
    return out


@dataclass
class AuditRunner:
    settings: Settings
    table: PricingTable
    engine: Engine
    mail: MailPort

    def wait_for_slot(self, timeout_s: float = 3600.0, poll_s: float = 0.1) -> bool:
        """NFR-13 admission: block while processing count >= cap."""
        factory = make_session_factory(self.engine)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with factory() as session:
                if processing_count(session) < self.settings.max_concurrent_audits:
                    return True
            time.sleep(poll_s)
        return False

    def run(self, audit_id: str) -> None:
        factory = make_session_factory(self.engine)
        if not self.wait_for_slot():
            log.error("runner.slot_timeout", audit_id=audit_id)
            return

        with factory() as session:
            audit = session.get(Audit, audit_id)
            if audit is None:
                log.error("runner.audit_missing", audit_id=audit_id)
                return
            audit.status = "processing"
            auditlog.append(session, "system", "audit.processing", audit_id)
            session.commit()

        try:
            self._pipeline(audit_id)
        except IngestError as exc:
            self._fail(audit_id, str(exc))  # IngestError messages are user-safe
        except Exception as exc:
            obs_errors.capture_exception(exc)
            self._fail(
                audit_id,
                "internal error while processing this audit — our team has been "
                "notified; contact support with your audit id",
            )

    def _pipeline(self, audit_id: str) -> None:
        factory = make_session_factory(self.engine)
        with factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None and audit.upload_path is not None
            upload_path = Path(audit.upload_path)
            user = session.get(User, audit.user_id)
            assert user is not None
            user_email = user.email

        # WP-PIPELINE-UI: wall-clock stamps at stage boundaries, persisted as
        # StageEvent rows in the final session — recorded at run time, never
        # estimated. Counts only in detail (FR-22).
        t_start = datetime.now(UTC)
        frame, vr = ingest.load(
            upload_path,
            max_upload_mb=self.settings.max_upload_mb,
            prefix_hash_chars=self.settings.prefix_hash_chars,
        )
        error_file = None
        if vr.errors:
            error_file = write_error_file(vr, upload_path.parent / "row_errors.csv")
        with factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            audit_user_id = audit.user_id
            audit.row_count = vr.total_rows
            audit.valid_pct = vr.valid_pct
            session.commit()
        enforce(vr, error_file)  # FR-03: aborts <95% via IngestError
        t_ingest = datetime.now(UTC)

        priced, unpriced = coster.apply(self.table, frame)
        total = coster.total_spend(priced)
        coster.reconcile(priced, total)  # NFR-07
        t_price = datetime.now(UTC)
        ctx = DetectorContext(
            settings=self.settings, table=self.table, observed_days=observed_days(priced)
        )
        findings: list[Finding] = run_all(priced, ctx)
        # Honest zeros: every detector appears, "ran, found nothing" included.
        by_detector: dict[str, int] = {d.name: 0 for d in DETECTORS}
        for f in findings:
            by_detector[f.detector] = by_detector.get(f.detector, 0) + 1
        t_detect = datetime.now(UTC)
        aggregates = aggregate(priced)
        report = ReportModel.build(
            audit_id=audit_id,
            priced=priced,
            findings=findings,
            unpriced=unpriced,
            table=self.table,
            generated_at=datetime.now(UTC).isoformat(),
        )
        # M-FLY-1 B1b: attach the peer-benchmark block when the cohort is
        # honest (dormant = the key never exists). DB-backed path only.
        with factory() as session:
            block = flywheel_benchmarks.report_block(
                session, self.settings, audit_user_id, own_value=report.savings_pct
            )
        if block is not None:
            report = dataclasses.replace(report, benchmark=block)
        report_dir = Path(self.settings.report_dir) / audit_id
        render_json(report, report_dir / "report.json")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.html").write_text(
            render_report_html(report, template="report.html"), encoding="utf-8"
        )
        render_pdf(report, report_dir / "report.pdf")
        t_report = datetime.now(UTC)
        stage_rows = (
            (
                "ingest",
                t_start,
                t_ingest,
                {"rows": vr.total_rows, "rejected": vr.total_rows - vr.valid_rows},
            ),
            (
                "price",
                t_ingest,
                t_price,
                {"priced_rows": len(priced), "unpriced_models": sorted(unpriced)},
            ),
            (
                "detect",
                t_price,
                t_detect,
                {"detectors": by_detector, "findings": len(findings)},
            ),
            ("report", t_detect, t_report, {"artifacts": ["json", "html", "pdf"]}),
        )

        with factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            # idempotent re-run (FR-19): replace previous derived rows
            session.execute(delete(FindingRow).where(FindingRow.audit_id == audit_id))
            session.execute(delete(CallAggregate).where(CallAggregate.audit_id == audit_id))
            session.execute(delete(StageEvent).where(StageEvent.audit_id == audit_id))
            for stage_name, started, finished, detail in stage_rows:
                session.add(
                    StageEvent(
                        audit_id=audit_id,
                        stage=stage_name,
                        started_at=started,
                        finished_at=finished,
                        detail=detail,
                    )
                )
            for f in findings:
                if len(f.evidence) > 20:  # defense in depth; enforced upstream too
                    raise ValueError("evidence sample exceeds 20 items")
                session.add(
                    FindingRow(
                        audit_id=audit_id,
                        finding_id=f.id,
                        detector=f.detector,
                        route=str(f.detail.get("model")) if f.detail else None,
                        severity=str(f.severity),
                        monthly_impact_usd=f.monthly_cost_impact_usd,
                        confidence=str(f.confidence),
                        fix_text=f.fix_text,
                        evidence_sample=[dataclasses.asdict(e) for e in f.evidence],
                    )
                )
            for row in aggregates:
                session.add(CallAggregate(audit_id=audit_id, **row))
            audit.observed_days = report.observed_days
            audit.equiv_spend = report.equiv_spend  # FR-30
            audit.total_spend_usd = report.total_spend_usd
            audit.projected_spend_usd = report.monthly_optimized_usd
            audit.savings_pct = report.savings_pct
            audit.provider_mix = report.provider_mix
            audit.status = "done"
            audit.report_ready_at = datetime.now(UTC)
            auditlog.append(
                session,
                "system",
                "audit.completed",
                audit_id,
                {"findings": len(findings), "unpriced_models": len(unpriced)},
            )
            session.commit()
        token = sign_report_url(self.settings.secret_key, audit_id)
        self.mail.report_ready(user_email, f"/r/{token}")  # FR-15 signed link
        log.info("runner.done", audit_id=audit_id, findings=len(findings))

    def _fail(self, audit_id: str, user_safe_message: str) -> None:
        factory = make_session_factory(self.engine)
        with factory() as session:
            audit = session.get(Audit, audit_id)
            if audit is None:
                return
            audit.status = "failed"
            audit.error = user_safe_message
            auditlog.append(session, "system", "audit.failed", audit_id)
            session.commit()
        log.warning("runner.failed", audit_id=audit_id)
