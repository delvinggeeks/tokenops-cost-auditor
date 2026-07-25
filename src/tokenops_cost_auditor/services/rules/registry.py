"""Ordered detector registry (FR-13; docs/03-LLD.md §1). Complete D1-D6 set."""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import Detector, DetectorContext
from tokenops_cost_auditor.services.rules.d1_oversized_model import D1OversizedModel
from tokenops_cost_auditor.services.rules.d2_missing_cache import D2MissingCache
from tokenops_cost_auditor.services.rules.d3_prompt_bloat import D3PromptBloat
from tokenops_cost_auditor.services.rules.d4_retry_storm import D4RetryStorm
from tokenops_cost_auditor.services.rules.d5_unbounded_max_tokens import D5UnboundedMaxTokens
from tokenops_cost_auditor.services.rules.d6_chatty_loop import D6ChattyLoop
from tokenops_cost_auditor.services.rules.d8_spend_concentration import D8SpendConcentration
from tokenops_cost_auditor.services.rules.d9_ineffective_cache import D9IneffectiveCache
from tokenops_cost_auditor.services.rules.d10_spend_anomaly import D10SpendAnomaly
from tokenops_cost_auditor.services.rules.findings import Finding

# Ordered: registry order is the tiebreak for equal-impact findings (stable output).
DETECTORS: tuple[Detector, ...] = (
    D1OversizedModel(),
    D2MissingCache(),
    D3PromptBloat(),
    D4RetryStorm(),
    D5UnboundedMaxTokens(),
    D6ChattyLoop(),
    D8SpendConcentration(),
    D9IneffectiveCache(),
    D10SpendAnomaly(),
)


def run_all(frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
    """Run enabled detectors in registry order; findings ranked by monthly $ impact
    (registry order then id as stable tiebreaks). Disable via settings.rules_disabled.

    Materiality floor (founder 2026-07-25, "work through what is worth fixing"): a
    SAVINGS finding always computes a STRICTLY-POSITIVE impact (a detector skips when
    there is nothing to save), so 0 < impact < settings.min_finding_monthly_usd means
    it would render as $0.00 — noise, not a finding, and is dropped so the list leads
    with real money. An INFORMATIONAL pointer (D5/D8/D10, D1-INFO) sets impact to
    EXACTLY 0.0 and is always kept — a $0 there means 'look at this', not 'worth
    nothing'. This drops noise without a detector allowlist."""
    disabled = set(ctx.settings.rules_disabled)
    floor = ctx.settings.min_finding_monthly_usd
    order = {d.name: i for i, d in enumerate(DETECTORS)}
    findings: list[Finding] = []
    for detector in DETECTORS:
        if detector.name in disabled:
            continue
        findings.extend(detector.run(frame, ctx))
    findings = [
        f
        for f in findings
        if f.monthly_cost_impact_usd == 0.0 or f.monthly_cost_impact_usd >= floor
    ]
    findings.sort(key=lambda f: (-f.monthly_cost_impact_usd, order[f.detector], f.id))
    return findings
