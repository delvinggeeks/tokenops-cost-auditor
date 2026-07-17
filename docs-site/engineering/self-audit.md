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

## The defect log: our own gates keep catching us

We publish our failures because the fixes are the credibility: the engine
cannot hallucinate, but its authors can, and the verification discipline is
what catches us.

**Defect one — the 228% savings claim.** Before launch, the founder ran the
audit on the real build sessions. The first run claimed **228% of spend as
savings** — a negative optimized projection. Two detectors priced
prompt-token savings at the full input rate, but ~95% of agent-session
prompt tokens are billed as cache reads at a tenth of that. Three more
defects surfaced in the same pass: agent sessions misread as retry storms,
an unbounded findings list that put an 18 GB document through the PDF
renderer, and no cap tying headline savings to observed spend. All four were
fixed with regression tests pinned before sign-off; the
[methodology](../report/reading-a-report.md) now discloses the as-billed
pricing rule and the savings cap.
<!-- src: pricing_golden_NOTES.md UAT-1 rows; UAT-1 founder sign-off 2026-07-18 -->

**Defect two — our verification gate refused our own first ledger row.**
The first self-audit row submitted for publication on this very page was
REJECTED in founder verification: the log exporter was emitting one row per
transcript *event* rather than one per completed API call, double-counting
spend (3,106 rows for 1,304 unique calls — one call echoed ten times).
Every figure from that run was discarded — the defective row never counts.
The exporter now deduplicates by request id and prints its dedup arithmetic
on every run; the ingest layer warns loudly on duplicate-heavy foreign logs;
and the retry detector treats same-id rows as one call by construction.
After the fix, measured waste went **up** (32.5% of a smaller, true spend) —
honest denominators cut both ways.
<!-- src: UAT-D5 founder verification refusal 2026-07-18; pricing_golden_NOTES.md UAT-D5 row -->

Corrected dogfood figures, resubmitted for founder verification and
publishable only once ticked in the ledger: 67,095 unique calls, ~$8,760
per month API-equivalent spend, ~$2,850 per month estimated waste (32.5%).
<!-- src: uat1 regenerated post-UAT-D5; pending founder tick per R-SELF-AUDIT c -->

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
