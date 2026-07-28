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

- **T-F5 · FR-38** — Issue #92 — showback CSV export: `dimension,name,calls,monthly_usd,
  share,pct_attributed_caveat` per LLD §9.5, figures verbatim from `tokenomics.json`,
  route + `/breakdown` affordance behind O-2 `MANAGE_BILLING`, honest empty/404 states ·
  trace: `services/dashboard` serializer + `routes_dashboard`→`test_showback` + journey.

## CANDIDATES — verified gaps; the founder sequences these into NOW

Not buildable yet (law 1: only a NOW task is buildable). Listed so the next session does not
re-derive them, and so they cannot be silently dropped (R-IMPROVISE).

- **T-D1 internal-docs refresh** — `CODE-TOUR.md` says "six detectors" (nine exist) and
  Part 2 lacks stops for platform API / orgs / payments / flywheel / statements; verify
  every stop against the current tree (registered 2026-07-28; entry point `docs/README.md`
  ships same day).
- **T-D2 diagram set refresh** — `docs/uml/` holds 2 pre-platform diagrams; add/refresh
  components + sequence diagrams covering read API, payments, orgs, flywheel
  (architect-gated per its charter — D6/D13-style pass).
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
- **T-F2 · FR-35** cohort export + consent — per-workspace opt-in flag; aggregate-only features
  (counts/ratios/percentiles, schema-versioned, k-floor n≥10 = the L1 threshold); tenancy
  stripped at the web/persistence boundary, engine stays tenant-blind (R-ORG) · overlaps
  `services/flywheel/{cohort,benchmarks}.py` — verify before building · trace: export
  golden + consent journey
- _(T-F3 → NOW 2026-07-28, Issue #89.)_
- **T-F4 · FR-37** realized-delta per finding — Applied-verdict findings (flywheel L0) get a
  next-audit drift delta attributed into the Savings Statement VERIFIED section (R-Q9
  provenance) · SCOPE-CHECK FIRST: `services/statements/build.py` already carries verified
  sections — measure the gap; this slice may shrink or collapse

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
