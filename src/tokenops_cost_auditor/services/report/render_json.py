"""Machine-readable report artifact (FR-14). Deterministic: same ReportModel
(with generated_at=None) renders byte-identical JSON — sorted keys, fixed
separators. No number is recomputed here (T-REP-01)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from tokenops_cost_auditor.services.report.model import ReportModel

SCHEMA_VERSION = 1


def report_to_dict(report: ReportModel) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": report.audit_id,
        "generated_at": report.generated_at,
        "pricing": {
            "version": report.pricing_version,  # FR-28
            "last_verified": report.pricing_last_verified,
            "unpriced_models": list(report.unpriced_models),
            "unpriced_model_count": len(report.unpriced_models),
        },
        "summary": {
            "observed_days": report.observed_days,
            "row_count": report.row_count,
            "provider_mix": report.provider_mix,
            "total_spend_usd": report.total_spend_usd,
            "monthly_spend_usd": report.monthly_spend_usd,
            "monthly_savings_usd": report.monthly_savings_usd,
            "monthly_optimized_usd": report.monthly_optimized_usd,
            "savings_pct": report.savings_pct,
            "equiv_spend": report.equiv_spend,  # FR-30
        },
        "spend_by_model": list(report.spend_by_model),
        "spend_by_day": list(report.spend_by_day),
        "findings": [
            {
                "id": f.id,
                "detector": f.detector,
                "severity": str(f.severity),
                "confidence": str(f.confidence),
                "monthly_cost_impact_usd": f.monthly_cost_impact_usd,
                "fix_text": f.fix_text,
                "evidence": [dataclasses.asdict(e) for e in f.evidence],
                # R-D6-AGG: per-run/per-cluster breakdown of aggregated findings
                # (counts and timestamps only, FR-22); null for others
                "detail": f.detail,
            }
            for f in report.findings
        ],
        "methodology": report.methodology,
        "data_handling": report.data_handling,
    }


def render_json(report: ReportModel, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        report_to_dict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    path.write_text(payload, encoding="utf-8")
    return path
