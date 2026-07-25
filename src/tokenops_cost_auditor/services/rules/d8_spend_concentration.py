"""Detector D8 — spend concentration (founder 2026-07-25, "richer findings").

Informational, not a saving: flags the route (tag) that carries a large share
(>= D8_CONCENTRATION_MIN_SHARE) of total audited spend, so the customer knows
where optimizing pays off most. Only meaningful when spend spans 2+ NAMED
routes — a single-route log is trivially 100% and is never flagged. Carries $0
direct impact (a pointer, like D5), severity low, confidence estimated.

Per-request only (needs route tags): INACTIVE_ON_AGGREGATE.
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    make_evidence,
    monthly_factor,
)


class D8SpendConcentration:
    name = "d8_spend_concentration"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        # unpriced rows carry NaN cost_usd — drop them so the share is honest.
        costs = frame[["tag", "cost_usd"]].dropna(subset=["cost_usd"])
        total = float(costs["cost_usd"].sum())
        if total <= 0:
            return []
        by_tag = costs.groupby("tag", sort=False)["cost_usd"].sum()
        # concentration is only meaningful across MORE THAN ONE named route; an
        # untagged bucket ("") is not an actionable route, so it never anchors.
        named = [t for t in by_tag.index if str(t).strip()]
        if len(named) < 2:
            return []
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        # sorted high→low, so every route BEFORE the first sub-threshold one
        # clears the bar — the break makes enumerate's index the flagged rank.
        for i, tag in enumerate(sorted(named, key=lambda t: -float(by_tag[t])), start=1):
            share = float(by_tag[tag]) / total
            if share < s.d8_concentration_min_share:
                break  # nothing after this clears the bar
            monthly = float(by_tag[tag]) * factor
            sub = frame[frame["tag"] == tag]
            findings.append(
                Finding(
                    id=f"D8-{i:03d}",
                    detector=self.name,
                    severity=Severity.LOW,
                    monthly_cost_impact_usd=0.0,  # a pointer, never a claimed saving
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"Route '{tag}' is {share * 100:.0f}% of your audited spend "
                        f"(about ${monthly:,.2f}/month). It is the highest-leverage place "
                        "to optimize first — the caching, model-sizing and prompt fixes "
                        "that touch this route move the most money. No direct saving is "
                        "claimed here; this points you where to look."
                    ),
                    evidence=make_evidence(sub, note="largest share of spend"),
                )
            )
        return findings
