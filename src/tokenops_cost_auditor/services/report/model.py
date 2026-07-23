"""ReportModel assembly (FR-14; docs/02-HLD.md C5).

Numbers are assembled HERE, once, from engine outputs — render layers (JSON, PDF,
web) must never recompute money math (T-REP-01). Monthly normalization follows the
accepted Q7 rule (x 30/observed_days) already recorded in the golden notes sheet.
FR-28: pricing table version/last_verified and unpriced models are part of the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tokenops_cost_auditor.services.pricing.coster import total_spend
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.rules.findings import Finding, monthly_factor, observed_days

# Methodology appendix (FR-14; R-GOLDEN-C3 floors + haircut disclosures).
METHODOLOGY = (
    "Every number in this report is computed deterministically from your uploaded "
    "logs by a rules engine that contains no AI model calls (NFR-01). "
    "Each call is priced at the provider rate in effect at its timestamp, from a "
    "versioned, human-verified pricing table; calls on models without a verified "
    "rate card are listed as unpriced and excluded from totals rather than guessed. "
    "Monthly figures normalize the observed window to 30 days (x 30/observed-days). "
    "Savings estimates are conservative by construction: cache savings subtract "
    "estimated cache-write costs (one write per cache-lifetime window, provider-"
    "specific) and apply a 0.7 haircut when write windows cannot be estimated; "
    "prefix identity without hash evidence takes a 20% suffix haircut; prompt-bloat "
    "savings assume only half the excess is removable; model-downgrade savings are "
    "computed at the suggested model's published rates and model suitability "
    "requires your own quality evaluation; savings on prompt tokens are priced as "
    "the tokens were actually billed (cache reads at cache-read rates, never the "
    "full input rate). Waste classes can overlap on the same calls, so the "
    "headline savings total is capped at your observed monthly spend; per-finding "
    "figures are independent estimates. Spend estimates are FLOORS: provider "
    "long-context surcharges and regional data-residency multipliers are not "
    "modeled in v1. Evidence rows carry token counts and metadata only — never "
    "prompt or completion text."
)

# FR-30 (R-EQUIV-SPEND, founder 2026-07-18) — verbatim; shown whenever metered-API
# billing cannot be assumed for the audited traffic (e.g. Claude Code exports).
EQUIV_SPEND_LINE = "Figures are API-equivalent token value; actual billing depends on your plan."

DATA_HANDLING = (
    "Your uploaded log file is analyzed and then deleted: raw uploads are "
    "automatically purged 7 days after report generation, purge events are written "
    "to an append-only audit log, and no prompt or completion text is ever stored. "
    "Retained data is limited to token counts, aggregates, and this report. "
    "Your logs and prompts are never used to train any model."
)


@dataclass(frozen=True)
class ReportModel:
    audit_id: str
    observed_days: int
    total_spend_usd: float
    monthly_spend_usd: float
    monthly_savings_usd: float
    monthly_optimized_usd: float
    savings_pct: float
    spend_by_model: tuple[dict[str, object], ...]
    spend_by_day: tuple[dict[str, object], ...]
    findings: tuple[Finding, ...]
    unpriced_models: tuple[str, ...]
    pricing_version: str
    pricing_last_verified: str | None
    provider_mix: str
    row_count: int
    methodology: str = METHODOLOGY
    data_handling: str = DATA_HANDLING
    generated_at: str | None = field(default=None)  # excluded from determinism
    # FR-30: metered-API billing cannot be assumed (subscription-plan traffic,
    # e.g. Claude Code exports) — header note + methodology line rendered
    equiv_spend: bool = False
    # M-FLY-1 B1b: peer-benchmark block; None = dormant = the JSON key never
    # exists (fixtures stay byte-identical). Set via dataclasses.replace by
    # the DB-backed callers only — the engine itself never computes it.
    benchmark: dict[str, object] | None = None
    # Presentation-only cap for HTML/PDF renderers (UAT-1 dogfood fix, D11):
    # an unbounded findings list let WeasyPrint lay out a ~30k-card document
    # (18GB RSS). JSON always carries EVERY finding; web/PDF show the top N by
    # impact plus an explicit "M more in report.json" line — never silent.
    render_cap: int = 50
    # v1.5 (PLAN-V15 R-Q1 / docs/12): which ingestion tier produced this audit
    # ("file" = upload/CLI, "account" = T2 connector) and the per-tier detector
    # coverage. Inactive detectors appear as labeled rows carrying NO savings
    # number — the honest-coverage law.
    tier: str = "file"
    coverage: tuple[dict[str, object], ...] = ()

    @classmethod
    def build(
        cls,
        audit_id: str,
        priced: pd.DataFrame,
        findings: list[Finding],
        unpriced: list[str],
        table: PricingTable,
        generated_at: str | None = None,
    ) -> ReportModel:
        days = observed_days(priced)
        total = total_spend(priced)
        monthly_spend = total * monthly_factor(days)
        # Waste classes can overlap on the same calls; an uncapped sum produced a
        # 228% savings claim and a negative optimized projection on real agent
        # traffic (UAT-1 dogfood fix, D11). Capped and disclosed in METHODOLOGY.
        monthly_savings = min(sum(f.monthly_cost_impact_usd for f in findings), monthly_spend)
        # FR-30: Claude Code exports come from subscription plans, not metered API
        equiv_spend = bool(len(priced) and (priced["endpoint"] == "claude-code").any())
        priced_rows = priced.dropna(subset=["cost_usd"])
        by_model: list[dict[str, object]] = [
            {
                "model": str(model),
                "calls": len(group),
                "cost_usd": float(group["cost_usd"].sum()),
            }
            for model, group in priced_rows.groupby("model", sort=True)
        ]
        by_day = [
            {"day": day.isoformat(), "cost_usd": float(group["cost_usd"].sum())}
            for day, group in priced_rows.groupby(priced_rows["ts"].dt.date, sort=True)
        ]
        return cls(
            audit_id=audit_id,
            observed_days=days,
            total_spend_usd=total,
            monthly_spend_usd=monthly_spend,
            monthly_savings_usd=monthly_savings,
            monthly_optimized_usd=monthly_spend - monthly_savings,
            savings_pct=(monthly_savings / monthly_spend * 100.0) if monthly_spend > 0 else 0.0,
            spend_by_model=tuple(sorted(by_model, key=lambda r: -float(r["cost_usd"]))),  # type: ignore[arg-type]
            spend_by_day=tuple(by_day),
            findings=tuple(findings),
            unpriced_models=tuple(unpriced),
            pricing_version=table.version,
            pricing_last_verified=(
                table.last_verified.isoformat() if table.last_verified else None
            ),
            provider_mix=",".join(sorted(priced["provider"].unique())) if len(priced) else "",
            row_count=len(priced),
            methodology=METHODOLOGY + (" " + EQUIV_SPEND_LINE if equiv_spend else ""),
            generated_at=generated_at,
            equiv_spend=equiv_spend,
        )
