"""FR-16 shareable sample report (PLAN-V15 V-D9 / WP-7).

Built by running SYNTHETIC fixture traffic through the REAL engine — the
same ingest → price → detect → assemble path a customer's upload takes. It
is not a mock-up and not a screenshot: every figure on the page is arithmetic
the shipped detectors produced, which is the only kind of sample an audit
product can honestly publish.

The data is the committed waste-pack fixture: invented traffic with planted
waste, no customer's numbers, nothing to redact.
"""

from __future__ import annotations

from pathlib import Path

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.pricing import coster
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_pdf import render_report_html
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import observed_days
from tokenops_cost_auditor.services.rules.registry import run_all

# Shipped WITH the package: a public marketing page must not depend on the
# test tree, which is absent from an installed wheel (V-D9 cold-review f.4).
FIXTURES = Path(__file__).parent / "sample_data"
SAMPLE_SOURCES = ("waste_pack_anthropic.jsonl", "waste_pack_openai.jsonl")
SAMPLE_AUDIT_ID = "sample00000000000000000000000000"
# Fixed so the page is byte-identical run to run (determinism is the product).
SAMPLE_GENERATED_AT = "2026-07-01T09:00:00+00:00"


def build_sample(settings: Settings, table: PricingTable) -> ReportModel:
    frames = []
    for name in SAMPLE_SOURCES:
        path = FIXTURES / name
        if path.exists():
            frame, _ = ingest.load(
                path,
                max_upload_mb=settings.max_upload_mb,
                prefix_hash_chars=settings.prefix_hash_chars,
            )
            frames.append(frame)
    if not frames:
        raise FileNotFoundError("sample fixtures are missing from the distribution")
    import pandas as pd

    combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    priced, unpriced = coster.apply(table, combined)
    ctx = DetectorContext(settings=settings, table=table, observed_days=observed_days(priced))
    findings = run_all(priced, ctx)
    return ReportModel.build(
        audit_id=SAMPLE_AUDIT_ID,
        priced=priced,
        findings=findings,
        unpriced=unpriced,
        table=table,
        generated_at=SAMPLE_GENERATED_AT,
    )


_RENDERED: str | None = None


def sample_html(settings: Settings, table: PricingTable) -> str:
    """Rendered ONCE per process and memoised — the inputs are committed
    fixtures that never change, and /sample is public and unauthenticated, so
    re-running ingest→price→detect per request would be free compute for
    anyone who wants it (V-D9 cold-review f.5)."""
    global _RENDERED
    if _RENDERED is None:
        _RENDERED = render_report_html(build_sample(settings, table))
    return _RENDERED
