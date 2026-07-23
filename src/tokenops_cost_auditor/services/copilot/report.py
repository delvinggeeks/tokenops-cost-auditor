"""Assemble a seat-governance report (WP-COPILOT-AGG, R-COPILOT, Option A).

The seat finding lands in the EXISTING report shell (not a token detector,
labeled seat governance). Reuses ReportModel/render like source_audit does
for its non-standard tier. equiv_spend=True is honest here for the same
reason it is for Claude Code: Copilot is a subscription, not metered API
billing, so the report prints "figures depend on your plan" — which is
exactly the caveat the seat rate needs.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, FindingRow
from tokenops_cost_auditor.services.copilot.seats import (
    DEFAULT_IDLE_DAYS,
    DEFAULT_SEAT_RATE_USD,
    analyze,
    build_finding,
    parse_seats,
)
from tokenops_cost_auditor.services.lifecycle import auditlog
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.report.render_pdf import render_pdf, render_report_html
from tokenops_cost_auditor.services.rules.findings import Finding

SEAT_METHODOLOGY = (
    "This is seat governance, not a token audit. The seat COUNTS and each "
    "seat's last-activity date are read deterministically from your uploaded "
    "export by code with no AI model calls (NFR-01); usernames and any content "
    "are never read (FR-22). A seat is counted idle when it has no activity in "
    "the window you chose. The recoverable figure is idle seats times the "
    "per-seat rate YOU entered (defaulting to GitHub's public list price) — a "
    "stated input, not a machine-verified rate, because SaaS seat prices are "
    "outside our token-price feed by design. This is a point-in-time snapshot "
    "of the export, not a scaled monthly projection. Reclaiming seats is your "
    "action in GitHub; we only surface the idle ones."
)

_COVERAGE: tuple[dict[str, object], ...] = (
    {
        "detector": "d7_idle_seats",
        "status": "seat_governance",
        "note": (
            "Seat governance, not a token detector: idle-seat counts are measured "
            "from your export; the per-seat dollar rate is your plan's price, "
            "confirmable, not a verified rate."
        ),
    },
)


def run_seat_audit(
    session: Session,
    settings: Settings,
    user_id: str,
    blob: str,
    *,
    idle_days: int = DEFAULT_IDLE_DAYS,
    rate_usd: float = DEFAULT_SEAT_RATE_USD,
    generated_at: str | None = None,
) -> str:
    """Parse a Copilot seat export -> a seat-governance report; returns the
    audit id. Raises ValueError on a malformed export (caller returns 400)."""
    seats = parse_seats(blob)
    summary = analyze(seats, idle_days=idle_days, rate_usd=rate_usd)
    finding: Finding = build_finding(summary)

    audit = Audit(
        user_id=user_id,
        status="done",
        paid_via="copilot-seats",
        provider_mix="github-copilot",
    )
    session.add(audit)
    session.flush()

    spend = round(summary.total * summary.rate_usd, 2)
    savings = summary.monthly_recoverable_usd
    report = ReportModel(
        audit_id=audit.id,
        observed_days=1,
        total_spend_usd=spend,
        monthly_spend_usd=spend,
        monthly_savings_usd=savings,
        monthly_optimized_usd=spend - savings,
        savings_pct=(savings / spend * 100.0) if spend > 0 else 0.0,
        spend_by_model=(
            {"model": "GitHub Copilot seats", "calls": summary.total, "cost_usd": spend},
        ),
        spend_by_day=(),
        findings=(finding,),
        unpriced_models=(),
        # not a token rate card — the seat rate is a stated input (R-COPILOT)
        pricing_version="seat-governance",
        pricing_last_verified=None,
        provider_mix="github-copilot",
        row_count=summary.total,
        generated_at=generated_at,
        equiv_spend=True,  # subscription, not metered — the honest FR-30 framing
        methodology=SEAT_METHODOLOGY,
        tier="seat-governance",
        coverage=_COVERAGE,
    )

    report_dir = Path(settings.report_dir) / audit.id
    report_dir.mkdir(parents=True, exist_ok=True)
    render_json(report, report_dir / "report.json")
    (report_dir / "report.html").write_text(
        render_report_html(report, template="report.html"), encoding="utf-8"
    )
    render_pdf(report, report_dir / "report.pdf")

    session.add(
        FindingRow(
            audit_id=audit.id,
            finding_id=finding.id,
            detector=finding.detector,
            route="github-copilot",
            severity=str(finding.severity),
            monthly_impact_usd=finding.monthly_cost_impact_usd,
            confidence=str(finding.confidence),
            fix_text=finding.fix_text,
            evidence_sample=[dataclasses.asdict(e) for e in finding.evidence],
        )
    )
    audit.row_count = summary.total
    audit.observed_days = 1
    audit.equiv_spend = True
    audit.provider_mix = "github-copilot"
    audit.total_spend_usd = spend
    audit.projected_spend_usd = spend - savings
    audit.savings_pct = report.savings_pct
    audit.valid_pct = 100.0
    audit.report_ready_at = datetime.now(UTC)
    auditlog.append(session, f"user:{user_id}", "copilot.seat_audit", audit.id)
    session.commit()
    return audit.id
