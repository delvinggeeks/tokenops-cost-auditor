# We audit ourselves

This product was built by AI coding agents whose sessions produce exactly the
logs the product audits. So we audit our own build, on a ledger, with the
same engine customers get — and publish the results here.
<!-- src: R-SELF-AUDIT (founder 2026-07-18); scripts/self_audit.py -->

Two honesty rails apply to every number on this page, verbatim:

- "Figures are API-equivalent token value; actual billing depends on your
  plan." <!-- src: FR-30 verbatim rail (R-SELF-AUDIT b) -->
- "n=1, uncontrolled — your logs are the real test."
  <!-- src: R-SELF-AUDIT b verbatim rail -->

And a verification rule: ledger rows are money-adjacent, so each published
row carries a founder-verification tick, logged exactly like our
[golden pricing files](testing.md) — unverified rows never render here.
<!-- src: R-SELF-AUDIT c -->

## The ledger

--8<-- "docs-site/engineering/self-audit-data.md"

## The UAT-1 story: our audit caught our own product lying

Before launch, the founder ran the audit on the real build sessions — 158,000
calls across 36 days. The first run produced a report claiming **228% of
spend as savings**, with a negative optimized projection. The audit was
wrong, and being wrong about money is the one thing this product must never
be.

The cause: two detectors priced prompt-token savings at the full input rate,
but ~95% of agent-session prompt tokens are billed as cache reads at a tenth
of that. Three more defects surfaced in the same pass: agent sessions
misread as retry storms, an unbounded findings list that put an 18 GB
document through the PDF renderer, and no cap tying headline savings to
observed spend.

All four were fixed with regression tests pinned before sign-off; the
[methodology](../report/reading-a-report.md) now discloses the as-billed
pricing rule and the savings cap. The final dogfood figures — 26.2% waste,
$5,289/month estimated on $20.2k/month API-equivalent spend, audited in 13
seconds — are what survived that process. We publish the failure because the
fix is the credibility: the engine cannot hallucinate, but its authors can,
and the golden-file discipline is what catches us.
<!-- src: STATUS.md D11 dogfood paragraphs; pricing_golden_NOTES.md UAT-1 rows; UAT-1 founder sign-off 2026-07-18 -->

## The intervention experiment

The audit's top recommendations apply to our own workflow. We are running
them on ourselves:

!!! warning "MEASUREMENT-PENDING (WP-SELF intervention)"
    Named interventions from our own UAT-1 report (prompt-caching hygiene on
    repeated agent context, batching chatty small-call loops) are being
    applied to the build workflow. Before/after deltas publish here once at
    least two post-intervention milestones exist in the verified ledger —
    not sooner, and with the same rails as everything else on this page.

## Run the same audit

The exporter and engine that produce these numbers are the shipping product:
[export your logs](../quickstart.md) and see your own ledger row. Nothing on
this page used any capability a customer doesn't get.
