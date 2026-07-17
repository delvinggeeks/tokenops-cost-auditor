"""Detector D5 — unbounded max_tokens (FR-11; docs/03-LLD.md §3).

Where declared_max_tokens is present in the logs: flag routes (tag, endpoint)
whose declared max p50 >= D5_MAX_RATIO x completion p95. Informational: the
finding carries $0 direct impact (latency/timeout risk note) unless the
provider bills reserved capacity (D5_RESERVED_BILLING config flag, default
false — no seeded provider does). Severity low, confidence estimated.
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    make_evidence,
)


class D5UnboundedMaxTokens:
    name = "d5_unbounded_max_tokens"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        declared = frame[frame["declared_max_tokens"].notna()]
        if len(declared) == 0:
            return []

        flagged: list[tuple[pd.DataFrame, str, str, float, float]] = []
        for (tag, endpoint), sub in declared.groupby(["tag", "endpoint"], sort=True):
            max_p50 = float(sub["declared_max_tokens"].quantile(0.5))
            completion_p95 = float(sub["completion_tokens"].quantile(0.95))
            if completion_p95 <= 0 or max_p50 < s.d5_max_ratio * completion_p95:
                continue
            flagged.append((sub, str(tag), str(endpoint), max_p50, completion_p95))

        findings: list[Finding] = []
        for i, (sub, tag, endpoint, max_p50, completion_p95) in enumerate(flagged, start=1):
            findings.append(
                Finding(
                    id=f"D5-{i:03d}",
                    detector=self.name,
                    severity=Severity.LOW,
                    monthly_cost_impact_usd=0.0,  # informational unless reserved billing
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"Route '{tag}' {endpoint or '(no endpoint)'} declares "
                        f"max_tokens around {int(max_p50)} while actual completions "
                        f"stay under {int(completion_p95)} tokens (p95). Oversized "
                        "caps inflate timeout budgets and worst-case latency, and can "
                        "reserve capacity on some plans. Set max_tokens near your "
                        "observed p95 plus headroom. No direct dollar impact is "
                        "claimed on your current providers."
                    ),
                    evidence=make_evidence(sub, note="declared max far above completions"),
                )
            )
        return findings
