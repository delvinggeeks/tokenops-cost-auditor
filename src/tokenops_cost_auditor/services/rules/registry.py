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
    (registry order then id as stable tiebreaks). Disable via settings.rules_disabled."""
    disabled = set(ctx.settings.rules_disabled)
    order = {d.name: i for i, d in enumerate(DETECTORS)}
    findings: list[Finding] = []
    for detector in DETECTORS:
        if detector.name in disabled:
            continue
        findings.extend(detector.run(frame, ctx))
    findings.sort(key=lambda f: (-f.monthly_cost_impact_usd, order[f.detector], f.id))
    return findings
