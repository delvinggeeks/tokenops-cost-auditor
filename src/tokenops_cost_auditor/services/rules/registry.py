"""Ordered detector registry (FR-13; docs/03-LLD.md §1). D1/D3/D5/D6 join at D5."""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import Detector, DetectorContext
from tokenops_cost_auditor.services.rules.d2_missing_cache import D2MissingCache
from tokenops_cost_auditor.services.rules.d4_retry_storm import D4RetryStorm
from tokenops_cost_auditor.services.rules.findings import Finding

# Ordered: registry order is the tiebreak for equal-impact findings (stable output).
DETECTORS: tuple[Detector, ...] = (
    D2MissingCache(),
    D4RetryStorm(),
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
