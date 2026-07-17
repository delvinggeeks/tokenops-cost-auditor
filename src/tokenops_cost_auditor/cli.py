"""CLI ingestion path (FR-04): `tokenops-cost-auditor audit file --out report.pdf`.

Offline concierge pipeline — no server, no database: ingest -> validate -> price
-> reconcile -> detect -> report (PDF + optional JSON). Exit codes: 0 ok,
2 usage error, 3 audit failed (bad input file).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.ingest.base import IngestError
from tokenops_cost_auditor.services.ingest.validator import enforce, write_error_file
from tokenops_cost_auditor.services.pricing import coster
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.report.render_pdf import render_pdf
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import observed_days
from tokenops_cost_auditor.services.rules.registry import run_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tokenops-cost-auditor",
        description="Deterministic LLM API spend audit — logs in, dollar-ranked report out.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    audit_cmd = sub.add_parser("audit", help="audit a log file and render the report")
    audit_cmd.add_argument("file", type=Path, help="OpenAI/Anthropic JSONL or generic CSV")
    audit_cmd.add_argument("--out", type=Path, default=Path("report.pdf"), help="PDF output path")
    audit_cmd.add_argument("--json", type=Path, default=None, help="also write report JSON here")
    args = parser.parse_args(argv)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    table = PricingTable.load()
    try:
        frame, vr = ingest.load(
            args.file,
            max_upload_mb=settings.max_upload_mb,
            prefix_hash_chars=settings.prefix_hash_chars,
        )
        error_file = None
        if vr.errors:
            error_file = write_error_file(vr, args.file.with_suffix(".row_errors.csv"))
            print(f"note: {len(vr.errors)} invalid rows -> {error_file}", file=sys.stderr)
        enforce(vr, error_file)
    except IngestError as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 3

    priced, unpriced = coster.apply(table, frame)
    coster.reconcile(priced, coster.total_spend(priced))
    ctx = DetectorContext(settings=settings, table=table, observed_days=observed_days(priced))
    findings = run_all(priced, ctx)
    report = ReportModel.build(
        audit_id=f"cli-{uuid.uuid4().hex[:8]}",
        priced=priced,
        findings=findings,
        unpriced=unpriced,
        table=table,
    )
    render_pdf(report, args.out)
    if args.json:
        render_json(report, args.json)
    print(
        f"report written to {args.out} — {len(findings)} finding(s), "
        f"${report.monthly_savings_usd:.2f}/month estimated savings "
        f"({report.savings_pct:.1f}% of ${report.monthly_spend_usd:.2f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
