# QUEUE — the single work spine

The one ordered, traceable list of what to build next. Agents read THIS top-to-bottom.
It does **not** copy the spec — it links it, and stays small on purpose (a big plan is
how agents hallucinate). Detail lives in the sources; sequence lives here.

## Sources (authoritative — link, never duplicate)

| Layer | Doc | Owns |
|-------|-----|------|
| WHAT | `docs/01-REQUIREMENTS.md` | FR/NFR + X-scope (the single requirement source) |
| DONE | `docs/04-TRACEABILITY.md` | req → module → test (proof of shipped) |
| HOW | `docs/09-SDLC.md` | slice lifecycle, DoD, gate set |

## Law (this is how we stop diverging)

1. Work **top-down from NOW**. One task = one vertical slice = one `loop:ready` issue, and it **cites its FR/NFR**.
2. **Nothing is built that isn't a NOW task here.** A new idea → `docs/01` (real scope) or `BACKLOG.md` (one line), never straight to code.
3. **Done = its `docs/04` row updated in the same PR** + gate round green. No other "done".
4. This file is the control surface, set up by hand; the **tasks on it go through the loop** (card → fresh session → reviewers → merge).
5. **Single flow (founder 2026-07-28).** An unshipped requirement lives as exactly ONE line
   in exactly ONE zone of this file (NOW / CANDIDATES / BLOCKED / PARKED). BACKLOG and the
   PLAN docs are reference detail, never a second queue — anything actionable there is
   surfaced here at reconcile, or it does not exist.
6. **Reconcile at session start.** Diff this file against open issues + the docs/04 tail:
   mark shipped, surface strays. A requirement found in any doc but absent here is a bug in
   the spine, fixed in the same session — never silently dropped (R-IMPROVISE).

## NOW — buildable, in order

_Reconciled 2026-07-28._ The 2026-07-26 "frontier exhausted" note is **superseded**: all 48
original FR/NFR remain shipped + traced (`docs/04`), but founder rulings since have opened new
scope — R-PLATFORM (API-first platform + enterprise: SDKs, MCP, SSO/SCIM), R-ORG
(workspaces/RBAC), R-IAM, and the payments pivot to real Standard Checkout. The frontier is
**open again**, and is now tracked by RULING, not by FR count.

_T-P8 SHIPPED 2026-07-28 — #86 merged (endpoint + SDK + docs/04 row, gates green)._

_T-D3 SHIPPED 2026-07-28 — BACKLOG/ROADMAP prune executed: known-stale pair fixed (API
keys deleted as shipped S-6; Orgs/SSO corrected to reflect R-ORG's relaxation, SSO itself
still parked behind O-3); ~28-bullet trigger register shrunk to one line + trigger each;
WP-P1.5/WP-P2-AGG/WP-MCP/View-report-link/Plain-English-PDF deleted as
shipped-or-superseded (found during the sweep, beyond the two named items);
WP-PIPELINE-UI + WP-REPORT-EXPLORER framing corrected to shipped-with-residue; ROADMAP §5
+ this file's S-3 line corrected (read tools shipped, write/parity still parked). Full
count in STATUS.md._

> Each task lands here as one line:
> `T-<id> · FR-xx | R-RULING · <vertical-slice one-liner> · trace: <module>→<test>`

_NOW order set 2026-07-28 (founder-delegated pick, session handoff): T-F3 → T-F5 → T-F2 →
T-D1 → T-D2. T-F1 enters when ruling ③ (factory repo name) lands; T-F4 follows T-F3 with
its scope-check first._

_T-F3 SHIPPED 2026-07-28 — Issue #89 slice: `services/dashboard/shapes.py` classifier
(LLD §9.3), shapes block in tokenomics.json, `/breakdown` chip column with fix-first dev
copy + pre-feature and coarse-depth honest states, verbatim API passthrough + sdk/js
types, docs/04 FR-36 row split out of the design span. T-F5 is next per the NOW order;
T-F4's scope-check may now run._

_T-F5 SHIPPED 2026-07-28 — Issue #92 slice: `services/dashboard/showback.py` serializer
(LLD §9.5 columns verbatim, artifact-byte figures, caveat on every row, honest empty
comment line), `GET /breakdown/showback.csv` behind O-2 `MANAGE_BILLING` (403/404 honest
states), owner-gated `/breakdown` affordance with visible showback gloss (ux mockup gate
PASS-WITH-NOTES, all 4 notes closed in-slice), docs/04 FR-38 row split out of the design
span. Next per NOW order: T-F2; T-F4's scope-check may run._

_T-F2 SHIPPED 2026-07-29 — Issue #95 slice: migration 024 `workspaces.cohort_opt_in`
(explicit opt-in, default false), `services/flywheel/export.py` CohortExportEnvelope v1
(LLD §9.1 verbatim — aggregate-only features, opaque `workspace_ref` in a key-space
disjoint from frame.py's, k≥10 floor with honest below-floor refusal naming n and the
floor), owner-gated Settings consent card (ux mockup gate PASS-WITH-NOTES, all 3 notes
closed in-slice), `GET /admin/cohort-export.json` + admin state row, docs/04 FR-35 row
split out of the design span. Next per NOW order: T-D1; T-F4's scope-check may run.

_T-D1 SHIPPED 2026-07-29 — Issue #99 / PR #101: CODE-TOUR verified stop-by-stop (nine
detectors, agent-verified pricing, Standard Checkout, 31 tables / chain 001→024) + four
Part-2 platform-era stops; README stale-register line cleared; docs-drift tripwire test
hardened across four gate rounds (no prefix allowlist, bare-filename + path::symbol()
citations fully resolved; round-4 system-tester FAIL closed by killing counted-detector
claims as a CLASS — nine customer surfaces made count-free, landing waste list completed
to d8/d9/d10, scan widened to templates/js/yaml). docs-site six-detector-era copy →
T-D4. Next per NOW order: T-F4 (shrunk scope) → T-D2._

_T-D2 SHIPPED 2026-07-29 — Issue #106: `docs/uml/` refreshed from 2 pre-platform (D6/D7
G4-sweep) diagrams to a 6-diagram platform-era set, drawn from the LIVE tree + import
graph (not spec snapshots): `components.mmd` (package-truthful map — web tenancy
boundary, engine-core tenant-blind grouping, platform services, workspace-spine
persistence, customer-side sdk/mcp/cli) and `audit-seq.mmd` (post-D7 tail: tokenomics +
shapes artifact, StageEvents, L1 benchmark attach, S-5 webhook dispatch; pre-D8 auth
stub note retired) refreshed; `read-api-seq.mmd`, `payments-seq.mmd`, `orgs-seq.mmd`,
`flywheel-seq.mmd` added. All six validated with mermaid-cli 11.16. Architect-gated in
the CI gate round (D6/D13-style pass). NOW is now empty — founder sequences the next
card from CANDIDATES (T-D4, T-D5) or a ruling._

## CANDIDATES — verified gaps; the founder sequences these into NOW

Not buildable yet (law 1: only a NOW task is buildable). Listed so the next session does not
re-derive them, and so they cannot be silently dropped (R-IMPROVISE).

- _(T-D1 → NOW 2026-07-29, Issue #99.)_
- _(T-D2 → NOW 2026-07-29, Issue #106.)_
- **T-D5 docs/05 test-plan refresh (FR-3x era)** — `docs/05-TEST-PLAN.md` §3 has no IDs
  for the v1.5+ slices (FR-36 shapes precedent; surfaced by the T-F5 vv gate note, which
  called the gap compounding). T-F5 added its own T-SHOW block in-slice; backfill the
  rest against the current tests/ tree (registered 2026-07-28).
- **T-D4 · FR-42** perf-claims reconcile — `docs-site/engineering/performance.md` says
  "all six detectors" (3×) with no era caveat while nine ship; FR-42 acceptance requires
  the caveat now and a nine-detector re-time on the measured machine to retire it
  (caught by the 2026-07-28 global law-6 audit — the FR landed with its acceptance
  already unmet and no slice).

**R-MODEL-FACTORY (founder 2026-07-28) — formalized as FR-34..FR-38 (docs/01 §H) with
HLD §8 + LLD §9 design deltas, per R-REQ-PIPELINE (docs/09 §9).** The learning lifecycle gets its own FACTORY: a
separate repo with eval-gated CI running daily; the platform consumes versioned model
artifacts behind a default-off flag; cross-workspace learning happens ONLY through an
opt-in, FR-22/R-ZTA-safe aggregate export. Dev-persona law (docs/12 INTENT + COPY LAW)
gets its first shipped surfaces. Slices:

- **T-F1 · FR-34** factory scaffold — separate repo (name: founder decides): eval harness + golden
  baselines + promotion gate + daily scheduled CI (evals-only until docs/12 §Stage-3
  thresholds fire — no training on n=1) · trace: factory CI green → platform artifact-loader test
- _(T-F2 → NOW 2026-07-28, Issue #95 — scope-check run at filing: existing flywheel
  modules verified non-covering.)_
- _(T-F3 → NOW 2026-07-28, Issue #89.)_
- _(T-F4 SHIPPED 2026-07-29 — Issue #102, shrunk scope per the T-D1-session scope-check:
  the credit mechanic pre-existed in `savings.py::compute()`; the slice delivered the LLD
  §9.4 attribution residue — `VerifiedLine(amount_usd, finding_ref, detector, from_audit,
  to_audit)` emission (detector added for the plain-copy lead, ux jargon law), the
  statement VERIFIED attributed lines with both audit-id stamps, the fr37 ≥7-day fixture
  pair, and the FR-37 acceptance journey. Totals verified unmoved — the pre-existing
  money-math goldens passed unchanged. Shipped as a RECONCILIATION on top of fb7d84b, a
  parallel loop-session implementation that reached main first with the 4-field line,
  un-gated bare-ref copy and a seeded journey — superseded test-by-test with the union
  kept; full record in STATUS.md.)_

- **T-T1 · LE-7 | R-TRACE** requirement-bound tests — registered pytest marker carrying the
  FR/NFR id becomes the SINGLE source of the requirement↔test edge (docs/04 becomes DERIVED, not
  authored), plus backfill of the current `tests/` tree; a marker naming an unknown id fails
  collection · trace: `tests/conftest.py` marker + backfill → `tests/test_traceability.py`
- **T-T2 · LE-8 | R-TRACE** traceability gate — CI fails on untraced requirement, dead test id,
  M-priority requirement with no passing bound test, missing module path, or **suspect link**
  (parent requirement content-hash changed since the link was last verified — the one control
  Doorstop has that the pytest-native options don't). Design-only requirements exempt BY
  DECLARATION, never by silence. **Sequence after T-T1** · trace: `scripts/trace.py check` +
  `.github/workflows/ci.yml` → `tests/test_trace_gate.py`
- **T-T3 · LE-9 | R-TRACE** traceability & delivery console — `scripts/trace.py` builds a derived
  index and serves it three ways: **CLI** (`status`/`walk`/`check`/`baseline`), a **generated
  static docs-site page** regenerated in CI (the auditor artifact — cannot drift), and a **local
  server-rendered htmx console** launched like `make preview` (bidirectional walk + a GENERATED
  agile board projecting QUEUE × issue/PR state, replacing the hand-maintained KANBAN.md stale
  since 2026-07-24 + the six flow metrics from issue/PR timestamps, zero estimation). Never
  mounted in the customer product. X-05-safe (SSR + htmx, no SPA, no build step) ·
  trace: `scripts/trace.py` + `web/templates/internal/` → `tests/test_trace_console.py`

_R-TRACE registered 2026-07-31 from a founder ask ("full traceability end to end for audit... for
auditing the requirements for humans" + "internal UI tool for human viewing and validating"),
analyzed per docs/09 §9 R-REQ-PIPELINE. **Homed as LE-7..LE-9, NOT as FRs** — requirement
traceability is SDLC/CI tooling, which per the docs/04 scope note is governed by CLAUDE.md rule 7
and docs/09 and owns no docs/04 row; registering it as FRs was self-contradictory (DoD item 10
would demand a matrix row the matrix forbids) and was corrected before merge. **Grounded in a
measured defect**: 22 of 63 test ids in docs/04 resolve to no collected test (incl. `T-RUL-D1-01..03`
for FR-07, a shipped core detector, absent from BOTH tests/ and docs/05), 3 requirements with no row,
and 148 of 192 test ids invisible to any document. Full rationale in docs/09 §6. Overlaps T-D5
(docs/05 test-plan refresh) — T-D5 folds into T-T1's backfill rather than running twice._

## BLOCKED — needs a founder action first (ROADMAP §4)

- Stripe/OAuth LIVE creds · domain cutover · UAT-2 · pending rulings — full list: `ROADMAP §4`.
- **Pending rulings 2026-07-28 — RESOLVED same day (founder, in-session):** ① T-D3
  sequenced into NOW · ② R-SCOPE-STOP recorded as a PARKED trigger · ④ chargeback REJECTED
  for now (revisit on customer pull; LIFECYCLE-MAP row updated) · ⑤ auto-merge flipped to
  rebase (squash rewrote author + added trailer). Still open: **③ factory repo name**
  (blocks T-F1 only).
- **Payments real-key testing (2026-07-28).** All four checkout slices are merged (#75 one-time
  INR, #80 INR subs, #78 one-time USD, #82 USD subs) and are code-complete + test-guarded, but
  each endpoint honestly 503s "checkout not switched on" until its keys are set. Founder lane:
  provider env keys + the provider-dashboard webhook endpoints. No agent work is blocked on this.
- (LE-2 continuous deploy is LIVE, not blocked — staging auto-deploys on every merge to
  `main`, verified `curl https://staging.tokenops-cost-auditor.com/healthz` →
  `{"ok":true,"db":true}`, same for prod. Branch protection on `main` is also LIVE. The
  only remaining deploy action is the founder-gated PROD **promotion** —
  `workflow_dispatch` after reviewing rendered staging pages — see ROADMAP §4.)

## PARKED — trigger-gated, do NOT pull forward (ROADMAP §5)

Each fires on a named customer/demand event. Pulling one forward without its trigger
**is** the divergence we're stopping.

- S-2 OTLP ← first streaming customer · S-3 MCP write-tools/get_audit-parity ← API-key
  signal (read tools shipped, Issue #54) · O-3 SSO ← first team customer
- M-FLY-2 calibration ← n≥25 peer data · D7 export detector ← day-45 · (full list: `ROADMAP §5`)
- L1 peer benchmarks ← n≥10 opted-in workspaces · L3 predictive ← n≥50 + 6mo history
  (docs/12 §Stage-3) · T5 gateway + L4 policy ← first in-VPC-blocking enterprise deal
- **R-SCOPE-STOP (recorded 2026-07-28, ruled from chat):** further read-API/agent surfaces —
  MCP `get_audit`/`get_breakdown` parity, `GET /api/v1/savings`, `GET /api/v1/sources`,
  drift-over-API — ← first programmatic-access request from a real customer
- **R-ENT-DEPLOY slice set (design docs/15 §8 · FR-39..42):** T-E1 Helm ← first VPC
  customer · T-E2 air-gap bundle ← first air-gapped deal · T-E3 marketplace IaC ← first
  marketplace lead · T-E4 Lane-A release train ← R-DEPLOY-AUTOMATION 2 trigger · T-E5
  Lane-B update channel ← rides T-E1

## Superseded for SEQUENCING → this file

`internal/ROADMAP`, `internal/PLAN(+PLAN-*)`, `KANBAN`, `BACKLOG`, `docs/07-ROADMAP`
still hold reference/design detail, but **what to build next comes from here** — not from them.
