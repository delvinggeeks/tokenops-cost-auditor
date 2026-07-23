# PLAN-FLYWHEEL.md — R-FLYWHEEL-TRAIN order breakdown (history → training → client intelligence → filterable reports)

Status: **RULED — R-EXPLORER (Q3), R-PROCEED (Q4/Q5/Q6/Q7), and
R-F1-SIGNOFF (2026-07-23: sentences ruled verbatim and applied; toggle
shipped, migration 015). Tracks A/B are unblocked; M-FLY-0 (A1+A2) is
the next flywheel milestone in queue order.**
Order source: founder, 2026-07-23 — "entire history of usage data to train
our own model · front gate for usage · preventive measures intelligently ·
customized solutions per client · client selects reports over all history
with multiple filter options."
Governing docs: docs/00-07, 09, 10, 11, 12; PLAN.md §0.0-0.1; PLAN-V15 §0.
Authoring tier per this order: PRD/design breakdown authored on Fable;
implementation milestones run on Opus; gate agents stay Sonnet (proposed
TE-5 amendment — question 5).

---

## 0. Coverage audit — the order mapped against the record

Everything below is evidence-cited (C-3 law). "SHIPPED" means code + tests
on main/v15-ui-unify today.

| # | Founder ask | Where captured | Status today | Gap |
|---|---|---|---|---|
| 1 | Entire history of usage data | docs/12 Stage 1 tiers T1-T5; R-CONNECT | **SHIPPED for T1/T2**: `connect_backfill_days=365` (config.py:208), usage-date gap scan + full-window back-dating (commit 2ac4b3e); T3 = WP-CC-LINK (post-launch, 2-3 days); T4/T5 trigger-registered | none — no new scope needed |
| 2 | Train our own model | docs/12 Stage 3 ladder L0-L4, HONESTY LAW | **L0 SHIPPED** (`finding_feedback`, models.py:260; verified-savings R-Q9); **L3 deterministic SHIPPED** (services/forecast.py, alert-only); **L1 NOT BUILT** (no benchmark code exists); **L2 NOT BUILT**; L4 = control-plane era | Tracks A + B below |
| 3 | Front gate for usage | docs/12 T5 GATEWAY; docs/07 P2-A; X-01 | Trigger registered + founder-approved 2026-07-22: first enterprise deal where procurement requires in-VPC deploy | **none buildable — X-01 stands**; this plan does not touch it |
| 4 | Preventive measures, intelligently | WP-3b alerts (observe-only), R-FLYWHEEL L3 forecast + overspend anomaly, R-DAILY-LOOP budget stages 50/80/100 | **SHIPPED** — everything preventive that is legal under X-02 today | L2 sharpens alert quality (Track B); enforcement stays forbidden until control-plane era (L4, human-approved) |
| 5 | Customized solutions per client | docs/12 L2 (Applied/Dismissed-trained thresholds); R-PERSONA/R-CLARITY depths | L0 labels flowing; calibration NOT BUILT | Track B slice B2/B3 |
| 6 | Client-selectable filtered reports over all history | **NOT CAPTURED ANYWHERE** — FR-31 gives a history *list* (deferred to WP-PIPELINE-UI); dashboard gives fixed 30/90d trends; zero filter surfaces exist (verified by grep) | new scope | **Track C — proposed FR-32; parked in BACKLOG per rule 1; needs PRD amendment** |

Reading of the order, stated honestly: items 1, 3, 4 are already shipped or
trigger-bound; the buildable substance is **L1 + L2 (Track B)** and the
**report explorer (Track C)**. "Train our own model" here means the ladder
docs/12 already defines — learned artifacts as DATA (thresholds,
percentiles, priors) consumed by the deterministic engine. It does NOT mean
an in-house LLM: NFR-01/X-04 forbid inference in the engine, and the
zero-token architecture (R-ZTA) is the moat — "we never burn your tokens to
count your tokens." Nothing in this plan weakens that.

## 1. Conflicts requiring founder rulings BEFORE any slice starts

**R-F1 — TRAINING vs THE PROMISE (the blocker).** "Never used for
training" is live, verbatim, on five surfaces: report body
(services/report/model.py:52), public shell footer
(_public_shell.html:114), Terms (terms.html:40), Privacy (privacy.html:7),
docs-site privacy page — and FR-23/T-POL-01 pin it by test. The ladder
threads the needle structurally (raw logs deleted; only counts/aggregates/
labels are retained per FR-21/FR-22) — but the promise as WORDED is
absolute. Options:

- **(A) RECOMMENDED.** Promise stays absolute for logs/prompts; copy is
  amended to say precisely what is true: "your logs and prompts are never
  used to train any model; anonymized usage counts and fix outcomes power
  cross-customer benchmarks every customer benefits from." Per-customer
  calibration (your labels tune your thresholds) proceeds without consent
  machinery; cross-customer aggregation (L1 benchmarks, L2 priors) rides
  the amended copy + a Settings opt-out. Requires: FR-23 wording amendment,
  Terms/Privacy edit, T-POL-01 update — founder-gated, same commit.
- **(B)** Copy untouched → cross-customer L1/L2 is OFF; only per-customer
  calibration ships. Ladder slows to per-account learning; the DATA moat
  ("clones start at n=0 forever") is forfeited.
- **(C)** Explicit opt-in benchmark program (consent flag, default off).
  Cleanest trust posture, slowest path to n≥10.

**R-F2 — Front gate confirmation.** Confirm item 3 changes nothing:
X-01/X-02 stand; T5 fires on its registered condition; "front gate" enters
the roadmap only through the control-plane era with the L4 policy grammar
(human-approved once, machine-enforced, audit-logged).

**R-F3 — FR-32 promotion.** The report explorer is new scope. This plan
drafts the requirement (§3 Track C); promotion needs a founder amendment in
docs/00-PRD.md. Until then it sits in BACKLOG (entry added:
WP-REPORT-EXPLORER).

**R-F4 — Where learned artifacts live.** Proposed: a new
`services/flywheel/` package (extraction, cohort ledger, benchmarks,
calibration proposals). `rules/` and `pricing/` stay untouched and under
the T-NFR-01 import guard; calibration output enters the engine ONLY as
threshold values through the existing config path — the guard never meets
an ML library. (No ML library is proposed at all — see §5.)

**R-F5 — Sequencing vs the standing queue.** The ruled queue is:
launch → WP-CC-LINK (2-3 d) → WP-PIPELINE-UI (first gated milestone) →
WP-P1.5 + WP-PLAT-0 (week 3). Proposal in §4 slots the new work around it
without reordering anything already ruled.

## 2. Uniform Definition of Done (every slice inherits; a slice is DONE only when all tick)

1. Tests per docs/05 ID pattern; full suite exit-code green (never grep).
2. Traceability row in docs/04 same commit (rule 5).
3. Money math → golden fixture + NOTES-sheet derivation same commit (rule 4).
4. FR-22 tier test wherever data crosses a boundary (counts-only allowlist).
5. Honesty law: every learned/benchmark output prints its training-population
   size; below-threshold surfaces render the MEASUREMENT-PENDING register —
   never invented numbers.
6. X-scope grep clean; T-NFR-01 import guard untouched and re-asserted.
7. New surfaces: static mockup gated by ux-reviewer BEFORE wiring
   (R-DESIGN); three-second rule; help-registry keys with plain + technical
   phrasing (T-HELP law); kit-composed (no new CSS dialects).
8. STATUS.md paragraph at milestone end; conventional commits; Dn all-green
   before Dn+1.
9. Human ownership: CODE-TOUR.md gains a chapter per new module in the same
   milestone; the module enters the TEACH curriculum (CLAUDE.md rule 8).
   No slice exceeds ~3 days or ~5 files of new surface — if it would, it
   splits.

## 3. Vertical slices

### Track A — training-data spine (prerequisite for all of Track B)

**A1 — TRAINING FRAME CONTRACT (1 day). SHIPPED 2026-07-23 (M-FLY-0).**
WHAT: `services/flywheel/frame.py` — deterministic extract of per-finding
training rows: {detector, bucket features (counts/timing/model only),
baseline_impact, L0 verdict, savings_realized, tier, provenance,
customer_pseudonym}. Column ALLOWLIST enforced in code; customer identity
pseudonymized via the existing HKDF module (context="flywheel-cohort"),
irreversible without SECRET_KEY. Runs as CLI/ops job only — never in the
request path, zero network.
AC: (1) extract deterministic given DB state; (2) schema test fails on any
column outside the allowlist and on any text-typed column by construction
(FR-22 tier test); (3) pseudonym stable per customer, non-invertible;
(4) import guard clean.
Tests: T-FLY-01..04. Traceability: new row "docs/12 L-frame".

**A2 — COHORT LEDGER (0.5-1 day). SHIPPED 2026-07-23 (M-FLY-0).**
WHAT: honesty-law plumbing — distinct customers with ≥1 completed audit /
with L0 labels / months of history; rung status vs thresholds (L1 n≥10,
L2 n≥25, L3 n≥50+6mo, from config). Surfaces: one daily-digest line
("flywheel: n=7 labeled — L1 dormant, needs 10") + admin panel row.
AC: (1) rung math tested at each boundary (9/10, 24/25); (2) thresholds
config-driven, never hard-coded; (3) digest line only — no customer-facing
surface until a rung is live.
Tests: T-FLY-05..06.

### Track B — learning ladder rungs (docs/12 Stage 3; build order L1 → L2-shadow → L2-active)

**B1 — L1 PEER BENCHMARKS, dormant-until-threshold (2 days).**
WHAT: nightly ofelia job precomputes waste-%/spend-mix percentiles over
pseudonymized cohort aggregates (Track A frame); dashboard + report gain a
"peer benchmark" section that renders ONLY at n≥10 and always prints
"based on N companies" (honesty law). Below threshold: the zero-state
register, exactly like the verified-savings headline precedent.
AC: (1) dormant below n=10 with honest register; (2) population printed on
every rendered number; (3) golden percentile fixture over a synthetic
12-customer cohort + NOTES derivation (money-adjacent law); (4) leakage
test: response contains percentile + n only — never another customer's
absolute figure or identifier; (5) help-registry keys at all three depths.
Tests: T-FLY-10..14. This is the "your waste = p75 of companies your size"
line — the first cross-customer moat surface.

**B2 — L2 THRESHOLD CALIBRATION, SHADOW MODE (2-3 days).**
WHAT: per (customer × detector), a deterministic calibration pass over
Applied/Dismissed labels proposes threshold values that maximize label
agreement — a transparent grid over the EXISTING config knobs (D3 bloat
bins, D4 window, D6 burst size…), not an opaque model. Artifact =
{current, proposed, labels_n, agreement_pct} persisted + shown in report
JSON calibration block and admin. Findings are UNCHANGED — shadow only.
AC: (1) engine untouched: report findings byte-identical with calibration
present vs absent (the golden-determinism gate IS the shadow guarantee);
(2) proposals render dormant below min labels (config
`l2_min_labels_per_detector`, proposed 10 — question 4); (3) agreement
math has a golden fixture + NOTES sheet; (4) `services/flywheel/` only —
import guard re-asserted.
Tests: T-FLY-20..24.

**B3 — L2 ACTIVE, per-detector founder flag (0.5 day; only after B2 has
≥1 month of shadow evidence).**
WHAT: admin action "apply proposed threshold" per customer × detector —
an audit-logged config write through the existing settings path. Applying
changes findings ⇒ the golden-update ritual applies in full (rule 4).
AC: (1) flag off by default everywhere; (2) every application audit-logged
with actor; (3) revert path tested; (4) X-02 untouched — thresholds tune
detection, never enforcement.
Tests: T-FLY-25..27.

**B4 — L3 learned upgrade. REGISTERED, NOT SCHEDULED.** The deterministic
forecast (shipped) stays the product until n≥50 + 6 months history per
docs/12. One BACKLOG line exists via docs/12; nothing to do now.

**B5 — L4 policy learning. Control-plane era. Untouched by this plan.**

### Track C — FR-32 REPORT EXPLORER (the genuinely new scope; needs R-F3)

Proposed requirement text (for the PRD amendment):
*FR-32 (M, post-launch): logged-in customers can compose a filtered view
over their ENTIRE retained history — filters: date range, provider, model,
source/tier, tag/endpoint, detector, severity, L0 feedback status —
rendered SSR+htmx as a report-grade page; every filtered total reconciles
±0.5% to the sum of its parts (NFR-07 law); purged audits participate as
metadata-only rows, degradation labeled honestly (FR-21/FR-31 law);
saved named filter sets per user.*

**C1 — filter backend (1-1.5 days).** Query layer over retained
`call_aggregates` + findings (raw purge-safe by construction); /api/v1
params + SSR partials.
AC: (1) reconciliation property test per filter dimension (±0.5%);
(2) auth-scoping test — no cross-user leakage (T-DASH-03 precedent);
(3) purged-audit rows metadata-only, labeled; (4) tier-coverage honesty:
a T2-only filter view states which detectors that tier cannot feed.
Tests: T-EXP-F-01..05 (docs/05 rows added same commit).

**C2 — explorer UI (1-1.5 days).** Static mockup FIRST → ux gate →
wire. Kit-composed (table_open, ribbon, computing_label — WP-PIPELINE-UI
vocabulary); filter chips + result table + drill-in to the standard
finding card; three depths copy; JS budget unchanged (htmx params, no new
library).
AC: three-second rule; T-HELP keys for every filter control; no new CSS.
Tests: T-EXP-F-06..08.

**C3 — saved views + export hook (0.5-1 day).** Named filter sets
(additive migration `saved_views`); "export this view" emits the SAME
counts-only JSON the data-export trigger describes — NOTE: shipping this
partially promotes the registered "data export" absence (R-SAAS-BASICS) —
flagged, question 6.
AC: saved-view roundtrip; export passes the FR-22 allowlist test; export
carries pricing version + tier-coverage block (FR-28 parity).
Tests: T-EXP-F-09..10.

### Track D — front gate + enforcement: NO BUILD. Trigger register only
(R-F2). The preventive surface a customer sees today — alerts, forecast,
digest budget stages — is complete for the pre-control-plane era.

## 4. Milestones, sizing, gate schedule

Slotted around the ruled queue; nothing already ruled moves.

| Milestone | Contents | Est. | Gate agents | When |
|---|---|---|---|---|
| (ruled) WP-CC-LINK | T3 collector | 2-3 d | per its own entry | immediately post-launch |
| (ruled) WP-PIPELINE-UI | runs/history surfaces | — | per its own entry | first post-launch gated milestone |
| **M-EXPLORER** | C1→C2→C3 | 3-4 d | vv + cold-reviewer + spec-guard + ux-reviewer | immediately after WP-PIPELINE-UI (shared surfaces, shared kit vocabulary) |
| **M-FLY-0** | R-F1..F5 rulings recorded + A1 + A2 | 1.5-2 d | vv + spec-guard | parallel-safe; can start the day R-F1 is ruled |
| **M-FLY-1** | B1 | 2 d | vv + cold-reviewer + spec-guard (money math) | after M-FLY-0; ships dormant regardless of n |
| **M-FLY-2** | B2 (+B3 flag, off) | 2.5-3 d | vv + cold-reviewer + spec-guard + architect (package boundary vs docs/03) | after M-FLY-1; B3 activation waits on shadow evidence |

All gates: TE-2 diff-only, TE-6 budgets, TE-8 verdicts, TE-11 pinned
toolchain; FAIL stops the milestone (TE-10); K-2 stop rule stands.
Standing regressions every gate: full suite exit-code green; golden report
JSON byte-identical; T-NFR-01; FR-23 verbatim (as amended if R-F1=A);
X-scope grep.

WP-PLAT-0 note: if the platform migration (week 3) lands before M-FLY-1/2,
`services/flywheel/` is born a workspace citizen (wa-detectors sibling);
the slices are written to survive either ordering — no shared files with
the migration's move set.

## 5. Scalability + improvement notes (recorded, not scope)

- **No ML dependency.** L1 is percentile arithmetic; L2 is a deterministic
  grid over existing knobs. Zero new runtime deps (R-DEPS holds). If a
  future rung genuinely needs one, that is a NEW founder dependency ruling
  — and it runs in an ops container, never in the serving image.
- **Request path untouched.** All flywheel computation is nightly ofelia
  jobs writing tables; dashboards read precomputed rows. The NFR-04 perf
  envelope and MAX_CONCURRENT_AUDITS admission are unaffected.
- **Explorer scale.** Filters run on retained aggregates (bounded rows),
  not raw uploads (purged anyway) — the 1M-row bound is an ingest-time
  cost, not an explorer-time cost.
- **Growth valves already registered** (no action): queue/workers trigger,
  stuck-audit auto-recovery, box upgrade on Team-tier load, k8s/T4
  attribution note, provider expansion queue (R-AGNOSTIC).
- **Cognitive-debt guard.** Every new module ≤ ~300 lines where feasible,
  one responsibility each; CODE-TOUR chapters + TEACH sessions are DoD
  items (§2.9), so the founder can hold the whole flywheel in the head —
  the codebase stays human-owned.

## 6. Numbered questions for founder ruling

1. **R-F1**: option A (amended copy + opt-out), B (copy untouched,
   per-customer only), or C (opt-in program)? A is recommended; the exact
   amended FR-23 sentence will be drafted for your sign-off before any
   copy/test change.
2. **R-F2**: confirm X-01/X-02 untouched; "front gate" remains the T5 /
   control-plane path on its registered trigger.
3. **R-F3 — RULED (founder, 2026-07-23, same-day follow-up order: "this
   selection is still not implemented in the dashboard").** FR-32 promoted
   (PRD amendment R-EXPLORER recorded) and built immediately: C1+C2 shipped
   on branch wp-report-explorer with the full DoD (§2). C3 saved views +
   export remains held on Q6 below. The §4 sequencing row for M-EXPLORER is
   superseded by this ruling.
4. **L2 activation floor**: per-customer calibration on own labels at ≥10
   labels/detector (proposed), while cross-customer priors wait for n≥25 —
   confirm both numbers.
5. **TE-5 amendment**: record "PRD/design breakdown authored on Fable;
   implementation milestones on Opus; gate agents Sonnet" in
   docs/10 §2 + CLAUDE.md rule 7. (Today's text reserves Opus for the main
   thread and PLAN authoring.)
6. **C3 export**: shipping "export this view" partially fires the
   registered data-export absence — ship it inside M-EXPLORER, or hold
   export until the registered trigger (first request / EU review) fires?
7. **Benchmark consent surface** (if R-F1=A): Settings toggle "include my
   anonymized counts in peer benchmarks" default ON with disclosure, or
   default OFF?
8. **Sequencing**: approve the §4 slotting (M-EXPLORER after
   WP-PIPELINE-UI; M-FLY-0..2 interleaved, never preempting the ruled
   queue)?

— END. Awaiting founder approval + rulings on §6. No application code
before approval.
