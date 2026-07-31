# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

## T-D3 — BACKLOG/ROADMAP prune (2026-07-28) — Issue #87, `loop:ready`

QUEUE law 5 (process): re-verified every BACKLOG.md item + the ROADMAP §4/§5 overlaps
against docs/04-TRACEABILITY.md and the code, docs-only. Counts: **6 shipped-deleted**
(API keys/programmatic access → S-6 read API+OAuth; WP-MCP → R-PLATFORM slice 2 read
tools; WP-P2-AGG Connect flows → V15 R-CONNECT; "in-app View report link missing" → PR
#28; "PLAIN-ENGLISH PDF REPORT" → PR #29; the WP-PIPELINE-UI "first post-launch gated
milestone" framing → FR-31 traced-done), **2 superseded-deleted** (WP-P1.5 pricing-watch
→ R-LIVE-PRICING auto sync, already noted in ROADMAP §6; WP-SKILL → folded into
WP-CC-LINK, R-CC-LINK 2026-07-23), **26 trigger-register items kept-live** (shrunk to one
line + named trigger each, no essays) plus WP-CC-LINK residue, WP-REPORT-EXPLORER
residue, the WP-PIPELINE-UI residue follow-ups (13 items, corrected/renumbered where a
sub-item had shipped), and 3 standing design/reference sections left unchanged
(R-DEPLOYMENT-CONTRACT, WP-FRAMEWORK-ADAPT, R-SAAS-BASICS — governing law, not scope
items). Both founder-flagged stale items fixed: "API keys" deleted as shipped; "Orgs/SSO
(X-03 stands)" corrected — R-ORG relaxed X-03 and workspaces/RBAC (O-0..O-2/O-4) shipped,
SSO itself stays parked behind O-3, first team customer. Bonus corrections found during
the sweep (R-IMPROVISE — surfaced, not silently dropped): WP-REPORT-EXPLORER's "saved
views HELD" claim was stale (saved views shipped with FR-32, only the export hook is
parked); ROADMAP §5 and QUEUE.md's S-3 MCP line said the whole server was trigger-gated
when read tools already shipped (Issue #54) — corrected to read-tools-shipped/write-
tools-parked in both files; the "six detectors" stale-copy backlog item was narrowed to
the one file (`docs-site/engineering/performance.md`) still saying six against nine.
BACKLOG.md: 544 → 329 lines. Zero code changes, zero QUEUE zone changes beyond the S-3
reconcile note and T-D3's own line marked SHIPPED. docs/04-TRACEABILITY.md untouched (no
new requirement implemented, none of the deleted items had rows there — they were
pre-implementation scope notes).

## FOUNDER-OWNED TASKS (consolidated order 2026-07-27 §4)

1. UptimeRobot public status page + CNAME status.tokenops-cost-auditor.com (runbook
   §3b, ~5 min) — the footer link must resolve BEFORE the launch thread.
2. Production walkthrough immediately after the unified-deploy verdict:
   clarity + function only, punch list by number, ACCEPT/HOLD.
3. Provider-side subscription closures whenever the daily digest flags one
   (manual until API-key adapters ship).
4. CLOSED 2026-07-27: founder verdict received filled — "F1-F10 confirmed
   fixed, exceptions: none. GO." Design deep-audit round closed; deploy
   authorized and founder-observed.

## GET /api/v1/audits/{id} — audit summary object (2026-07-27) — Issue #72, `loop:ready`

Developers could create/list audits and read findings, but there was no single call for the
audit's OWN summary (totals, cost, counts, scope, timing) — they'd scrape it from the HTML
report or stitch `/audits` + `/audits/{id}/findings` together. SHIPPED: NEW
`GET /api/v1/audits/{audit_id}` in `web/routes_api_read.py`, alongside the existing
`list_audits`/`list_findings` handlers — SAME `read:audits`-scoped `ReadPrincipal` dependency
and `active_workspace_id` tenancy check as `GET /api/v1/audits`, no new auth path invented.
Returns `id, status, scope_label, created_at, completed_at,
totals{calls, input_tokens, output_tokens, total_tokens, estimated_cost_usd}, model_count,
finding_count`. Totals are summed from the audit's own `CallAggregate` rows (calls/
prompt_tokens/completion_tokens, distinct `model` for `model_count`); `estimated_cost_usd`
reads straight off `Audit.total_spend_usd` — the exact figure the downloadable report shows,
not a parallel recomputation. `scope_label` reuses the existing `Audit.provider_mix` column
(e.g. `"anthropic"`) rather than inventing a new derivation. An audit that hasn't reached
`status="done"` yet has no `CallAggregate` rows written (the runner only writes them at
completion), so the summary comes back with honestly zeroed/`null` totals and its real
in-progress `status` — never a 500. Cross-workspace id → 404 (same existence-oracle-closed
rule as `/findings`); a token missing `read:audits` → 403. FR-22: counts/dollars/metadata
only — no prompt/completion text exists to return, asserted at the response-shape level.
Tests: NEW `tests/test_developer_platform.py::TestGetAuditSummary` — a REAL upload→run
pipeline audit (`waste_pack_anthropic.jsonl`) whose summary totals are independently
cross-checked against its own `CallAggregate` rows AND the report.json's `total_spend_usd`
(not literals); cross-tenant 404; missing-scope 403; an incomplete (`status="running"`)
audit returns zeroed/null totals never 500; FR-22 response-shape check (exact key set, no
prompt/completion/content substrings). `docs-site/api/reference.md` gained a "Get an audit's
summary" section; `docs-site/api/endpoints.md` regenerated via `scripts/export_openapi.py`
(`--check` clean); `tests/test_docs_site.py::TestApiReferenceAccuracy` REQUIRED_V1_ENDPOINTS
gained the new route. No SDK method this slice (out of scope per the issue — a Python/JS SDK
`getAudit()` wrapper is a fast-follow). Engine untouched (T-NFR-01 — this lives entirely in
`web/`). Full pinned toolchain green (`ruff check`/`ruff format`/`mypy`/`pytest -m 'not perf'`).
docs/04-TRACEABILITY.md row added (R-PLATFORM slice 7).

## CCY TOGGLE — visible USD|INR override on /pricing + /billing (2026-07-27) — Issue #70, `loop:ready`

#68 taught the server to auto-detect region (IP→country) but left a visitor who wants the
OTHER currency with no visible control — the `?ccy` precedence existed but nothing SET it
in the UI once the old timezone-cookie JS was ripped out. SHIPPED: a compact two-option
`kit.ccy_toggle` macro (`kit/_kit.html`) — a live segmented "USD $ | INR ₹" control on
`/pricing` and `/billing`'s plans section; clicking a currency navigates with `?ccy=` and
the server sets the `ccy` cookie on THAT response so the choice persists to the next page
with no `?ccy` needed. `/billing` was the one of the three render sites (landing/pricing/
billing) that #68 wired for READING the cookie but never for SETTING it — folded in here.

HONESTY RAIL (the point of the issue): a currently subscribed account is locked to its
subscription's billing currency and must see STATIC text — "USD $ — billed in USD on your
plan." — never a control that looks live but silently won't switch. NEW
`plans.locked_currency(session, user_id) -> str | None`, extracted from `viewer_currency`
(now a thin wrapper over it) so routes can also use it to pick the template's rendering
mode. IMPROVISED FIX folded into the same slice (R-IMPROVISE — an honesty gap found while
building, not parked): the old `viewer_currency` locked ANY account with a Subscription row
regardless of status, including CANCELLED ones — invisible before (a cancelled account's
toggle silently no-op'd, unnoticed), but about to become a VISIBLE lie the moment a static
"billed in X on your plan" note renders for someone who isn't actually being billed.
`locked_currency` now excludes `status == "cancelled"` (compared as a literal to avoid a
plans↔subscriptions import cycle) — a cancelled account reverts to a live, working toggle.

`?ccy` still wins over the cookie and over geo — precedence from #68/#69 is unchanged.
No price VALUE changed. FILE MAP: `services/payments/plans.py` (+`locked_currency`,
`viewer_currency` refactored); `web/routes_pages.py::pricing_page` + `web/routes_billing.py
::billing_page` (compute `locked`, pass `currency_locked`, set the cookie honestly —
skipped when locked); `web/templates/kit/_kit.html` (+`ccy_toggle` macro); `pricing.html` +
`app/billing.html` (old inline "India pricing · toggle-link" markup replaced by the shared
macro — ONE place both screens say the same thing the same way); `wa-design.css`
`.ccy-toggle`/`.ccy-toggle-locked` (both the served copy and `docs/design/wa-design.css`
source, design-asset parity). Tests: tests/test_pricing_page.py::TestPricingPageCurrencyToggle
(toggle click redraws real catalogue money + sets the cookie; cookie persists on a later
request with no `?ccy`; explicit `?ccy` overrides a prior cookie) + tests/test_subscriptions.py
::TestBillingCurrencyToggle (same three for `/billing` + a subscribed account sees the
locked static note and never the live markup even against a stray `?ccy` + a CANCELLED
subscription is confirmed NOT locked). Full suite green (`ruff`/`ruff format`/`mypy`/
`pytest -m 'not perf'`), coverage gate green (services 96.4%, coster.py + findings.py
100%). docs/04-TRACEABILITY.md row added.

## PROCESS FIX — the experience gate + staging-review-before-prod (2026-07-25) — founder "why are these issues reaching prod despite spec/gates/CI-CD?"

ROOT CAUSE (honest): the pipeline is strong on CORRECTNESS (spec + 5-agent gates + CI +
golden money) but blind to EMERGENT, whole-surface, real-data quality — and it
AUTO-SHIPPED to prod on a healthz smoke, so the founder was the first human to see the
rendered product = the founder became QA. Per-slice diff gates on CLEAN fixtures cannot
see a cluttered findings list, a figure page that forgot the honesty banner, or a
duplicated CTA (each slice was correct alone). TWO structural fixes shipped:
(1) EXPERIENCE GATE — tests/test_experience_walkthrough.py renders the KEY authenticated
surfaces with a REAL audit + nothing connected and asserts the LIVED-quality invariants
per-slice gates miss: the honesty banner on EVERY figure page (cross-cutting contract,
not a hand-list a new page can forget), /findings clean + route-named, /sources connect
CTA exactly ONCE. It runs in CI (regular + the deploy `gate` job), so this class of
regression now fails BEFORE staging. It CAUGHT the two live bugs on first run.
(2) STAGING-REVIEW-BEFORE-PROD — deploy.yml: prod deploy is now gated `if:
github.event_name == 'workflow_dispatch'` — every merge auto-deploys STAGING only; prod
is a MANUAL founder promotion after reviewing the real pages on staging. Reconciles the
pipeline with the founder's standing "prod deploy is my gated step". FIXES it drove:
_shell.html _figure_pages +"breakdown" (the /breakdown honesty-banner gap); sources.html
add-bar connect buttons only render when a connection already exists (empty state is the
single CTA — the mangled duplicated-CTA bug). All green; CSS parity intact (templates
only).

## FINDINGS CLARITY — materiality floor + route naming (2026-07-25) — founder "work through what is worth fixing, largest dollar impact first" (prod /findings showed $0.00 + duplicate-looking findings)

Founder pasted prod /findings: 11 findings on a 46,868-call/86-day audit, several worth
$0.00, and the same plain-English text ("One route's prompts are far larger…") repeated
7× because the list never named WHICH route. Two defects, both fixed:
(1) MATERIALITY FLOOR — a SAVINGS finding always computes a strictly-positive impact (a
detector skips when there is nothing to save), so `0 < impact < min_finding_monthly_usd`
($0.005 default, configurable) means it renders as $0.00 = noise → dropped in run_all; an
INFORMATIONAL pointer (D5/D8/D10, D1-INFO) sets impact to EXACTLY 0.0 and is always kept
(a $0 there means "look at this"). No detector allowlist needed — the 0.0-vs-positive
invariant does it. Verified on waste_pack: a huge floor leaves ONLY D5 ($0.0), all savings
dropped. (2) ROUTE NAMING — D1/D2/D3/D9 now carry detail["route"] (the model or tag they
flag); runner persists FindingRow.route from detail.route‖model; the /findings row renders
"…on `<route>`" so many findings of one kind read as DISTINCT. FILE MAP: registry.run_all
(floor); config.min_finding_monthly_usd + .env.example; d1/d2/d3/d9 detail["route"];
runner FindingRow.route; routes_dashboard items +route; findings.html row +route.
+tests/test_rules.py::TestFindingsClarity (floor drops savings/keeps informational;
default floor keeps all 6 waste_pack findings; savings findings name their route). Money
values UNCHANGED (no golden) — this only DROPS $0-noise and NAMES findings. Next: banner
coverage on /breakdown + all figure pages; then Sources page redesign; then O-2 RBAC.

## ROADMAP CONSOLIDATION — single source of truth (2026-07-25) — founder "we have a lot of requirements which we got diverted ... single source of truth and not missed or diverted"

Founder course-correction: the depth-engine slices (tokenomics/D10/drift) grew from an
improvised "more findings" thread and diverted from the planned requirement order (after
O-1, the plan's next milestone was O-2 RBAC). Requirements were scattered across ~18 plan
docs with no consolidated view, which is HOW the divergence went uncaught. FIX: a full
5-way parallel sweep of every plan/requirement doc → consolidated into **docs/internal/ROADMAP.md**
(the single source of truth): §0 shipped baseline · §1 X-guardrails · §2 process + DoD ·
§3 buildable-now frontier (9 items, prioritized; O-2 RBAC is #1) · §4 founder-owned ·
§5 trigger-gated (parked by design) · §6 reconciliations. KEY FINDING: all FR-01..32 /
NFR-01..15 are traced-done; nearly all outstanding work is DELIBERATELY trigger-gated or
founder-owned — not forgotten. Supersedes the stale KANBAN.md 2026-07-24 snapshot as the
working queue. PROCESS RULINGS: work §3 top-down,
no task-tool kanban (track in STATUS + ROADMAP), each slice FULLY covers its req (R-VERTICAL),
new ideas go to §5 not into code. Next build: O-2 Roles/RBAC.

## CROSS-AUDIT DRIFT — Breakdown "vs your last audit" (2026-07-25) — founder "proceed as recommended next step" (the drift half of anomaly & drift)

On branch `cross-audit-drift` off main (b995ddc). Second half of the founder's chosen
"anomaly & drift detection": after D10 within-audit spikes (PR #21, held for merge),
this ships CROSS-AUDIT efficiency drift — the Breakdown page gains a "Trend vs your
last audit" section comparing THIS audit's tokenomics vitals to the PRIOR audit's.
services/dashboard/drift.py: PURE deterministic diff of two tokenomics.json artifacts
(the exact figures the runner already wrote) — like-for-like over time, so a change is
a real TREND, not the cross-sectional "which route is heavier" confound. Direction is
judged ONLY where "good" is unambiguous: cost-per-request and cost-per-1k-output UP =
worse, cache-hit DOWN = worse; monthly spend is CONTEXT with no verdict (more spend can
just mean more usage — calling it a regression would be dishonest). A sub-5% change is
"flat" (noise). A regression callout fires when any efficiency metric materially
worsens. FILE MAP: +drift.py; metrics.recent_done_audits (2 most recent DONE audits,
workspace-scoped); routes_dashboard._load_tokenomics helper + breakdown_page loads
current+prior tk and computes drift (honest: needs BOTH artifacts — a pre-tokenomics.json
audit yields no trend, never half a comparison; corrupt/missing → no 500);
breakdown.html "Trend vs your last audit" kit-composed table (current/prior/change/trend,
role-token verdict colours inline like the drawer) + regression callout + honest "run
another audit" empty state. +tests/test_drift.py (6 pure: better/worse/flat/context/
spend-down/prior-zero-guard, hand-derived deltas) + tests/test_drift_journey.py (two
real audits → trend + regression renders; single audit → honest empty state) +
tests/fixtures/drift_prior.csv (efficient) + drift_current.csv (worse). NO new estimator
(diffs already-priced figures) → no golden owed. Deterministic, FR-22 counts-only.
INDEPENDENT of PR #21 (needs only tokenomics.json from #19, already on main) — branched
off main; STATUS/help text may conflict with #21 at merge (resolve keeping both, as #19→#20).
GATE ROUND (spec PASS · vv PASS · ux/system PASS-WITH-NOTES · cold FAIL→fixed→re-run):
cold f.1 (the real bug) → a money metric with prior==0 (a prior audit with $0 priced
spend) was dishonestly flagged "worse"/regression; now prior==0 yields "new" (no
percentage baseline → never a better/worse verdict, never a regression), matching the
"new" the Change column already showed. cold f.2 → recent_done_audits gains an
Audit.id.desc() tiebreak so equal-created_at audits never swap current/prior. cold f.3
+ vv → +test for money prior==0 (never a false regression) and the rate prior==0 test
updated to "new". ux f.4 → the no-prior empty state is now kit.empty_state with a
one-click action (Upload another log / Connect a source), consistent with the page's
other empty state. ux f.5 → "unit economics" glossed on first use. system-tester note →
+workspace-isolation journey test (user B never sees user A's trend). drift.py stays
100% covered; full suite green.
## SPEND ANOMALY — D10 detector, depth-engine "dynamic analysis" (2026-07-25) — founder "proceed next", chose "Anomaly & drift detection"

On branch `anomaly-detection` off main (b995ddc). Next deterministic depth-engine
slice = the "dynamic analysis based on logs" the founder repeatedly asked for.
Shipped **D10 spend anomaly** (`services/rules/d10_spend_anomaly`): robust temporal
spike detection over the audit's OWN daily-spend series — median + MAD, NOT mean +
std, so a spike cannot inflate its own baseline and hide (a std-based detector
would). A day flags only when it clears TWO scale-free gates — statistical
(>= d10_z_threshold=3.5 MADs above the median day; on a perfectly flat baseline z
is undefined and the gate is carried by materiality) AND materiality
(>= d10_spike_mult=2.0x the median) — over a weekly baseline (>= d10_min_days=7).
Both gates are scale-free, so window length never dilutes a real spike (the
excess-share-of-total gate was DROPPED in the gate round — cold-reviewer f.3:
it caused a window-length-dependent false negative on long audits and was
redundant with the multiple gate). Self-referential (each
day vs the customer's OWN typical day), so a legitimately heavier route is NEVER
mistaken for waste (the founder's 100%-precise bar). INFORMATIONAL: $0 claimed (like
D8) — an unnamed spike has no known fix, so we never invent a saving; complementary
to the pattern detectors (D4/D6/D1 price the recoverable part on the same day, not
duplicated). Honestly DORMANT below the weekly baseline and on aggregates
(INACTIVE_ON_AGGREGATE — the aggregate path prices buckets itself). Each spike
attributes its top DRIVER (model + route). NO new rate/estimator (sums the coster's
cost_usd + statistics) → NO golden owed; pinned by hand-derived RATE-INDEPENDENT
multiples (day/median cancels the rate). FILE MAP: +d10_spend_anomaly; registry
DETECTORS + INACTIVE_ON_AGGREGATE (+d10); config d10_* + .env.example; help_registry
d10 entry + help._threshold_values (+4); +tests/test_rules.py::TestD10 (11 cases:
rate-indep golden multiple, driver attribution, dormancy, flat-silent, robustness,
each of 3 gates, untagged, chronological ids, short-fixture dormant) +
tests/test_spend_anomaly.py (journey: 7-day spike fixture → real audit → reachable
/findings + drawer plain-English BOTH audiences) + tests/fixtures/spend_spike.csv;
test_dashboard help-count(8→9), test_source_audit coverage(8→9), test_aggregate_rules
INACTIVE list. Surfaces through the EXISTING finding UI (Findings + drawer) — no new
route, no endpoints.md drift. Engine pure (T-NFR-01), FR-22 counts-only. OPEN
(parked BACKLOG, NOT silently changed): the "six detectors" customer copy
(landing/first-run/findings/tour/docs) is stale — engine now runs 9 (d1-6 savings +
d8/d9/d10 informational); needs a deliberate messaging refresh (savings-finders vs
informational insights) with the ux gate, not a mid-slice find-replace.
GATE ROUND (all 5 PASS-WITH-NOTES, full suite green, notes ACTIONED): cold f.1 →
severity now anomaly-native by the deviation MULTIPLE (>=10x HIGH, >=4x MED, else
LOW), not the monthly-USD scale; f.2 → test_05 rewritten to genuinely demonstrate
robustness (two mutually-masking spikes a mean+std detector misses — asserted z<bar
— but median+MAD catches both); f.3 → dropped the window-dependent excess-share
gate (two scale-free gates now); f.4 → docstring softened + day-of-week/seasonal
baseline parked (BACKLOG). ux f.1/f.2 → the $0.00 waste headline is replaced by an
honest "Informational" chip for D5/D8/D10 in _finding_drawer.html; the per-incident
figure prominence (needs FindingRow.detail persisted) parked (BACKLOG). vv f.2 →
+3 guard-branch tests (empty / all-unpriced / median<=0). spec f.1 → requirements.md
FR-33 amendment (R-DEPTH-ENGINE) backfills the D8/D9/D10 depth detectors formally.
system-tester → all PASS (reachable, dormant-honest, no regression, aggregate-inactive).

## PROXY-HEADERS FIX (2026-07-23) — the S-0 verify surfaced a pre-existing prod rate-limit gap

The final S-0 security verify (PASS, no bypass) flagged an operational
caveat that turned out to be LIVE in our own prod: uvicorn ran without
--proxy-headers, and the app is `expose`-only behind Caddy, so
request.client.host was Caddy's container IP for EVERY request — ALL
IP-based rate limits (the new ingest 300/min ceiling AND the pre-existing
magic-link / unauthenticated limits) collapsed into ONE global bucket.
Not an S-0 regression — a latent issue since first deploy that the ingest
work surfaced. Fixed in the Dockerfile CMD: --proxy-headers
--forwarded-allow-ips="*" (safe because the app port is never published —
only Caddy on the internal network can reach it, so only Caddy can set
X-Forwarded-For, which Caddy sets by default). get_remote_address now
sees the real client IP. Not exercised by pytest (server-layer flag;
TestClient is unaffected) — takes effect on the NEXT deploy. HONEST
DISCLOSURE: live v1.7.0 still has the global-bucket behaviour until then;
impact is bounded (per-key ingest fairness is unaffected — it keys on the
bearer token, not IP; token entropy defeats guessing regardless), so this
rides the next scheduled deploy rather than forcing an emergency one.

## SHIPPED TO MAIN (2026-07-25) — founder "open PRs + merge both to main"

Both slices merged via the GO-FORWARD PR flow (full CI: authorship·lint·type·
docs·test·build all green). **PR #15 O-1b-3** (1077701) — CLOSES O-1. CI caught
two real gate failures a locally exit-masked `pytest | tail` had hidden — a
`{{ m.email }}` in a data-confirm (test_authority_laws) and a stale endpoints.md
(MP-3 drift, the 3 new routes) — both fixed, re-verified with pytest's OWN exit
code, re-gated green (LESSON reinforced in [[never-mask-pytest-exit]]: never trust
a piped pytest's exit; capture `$?` un-piped). **PR #16 coherence** (18f14e2) —
rebased onto O-1b-3, STATUS+traceability conflicts resolved keeping both. main is
now well ahead of prod (v1.9.0=O-0) by the entire O-1 stack + coherence; the prod
deploy stays founder-gated (deploy secrets + one validated run). NEXT theme
(founder-chosen): guided first-run + output preview (punch-list #4/#5).

## LANDING — RELATABLE MESSAGING (2026-07-25) — founder "marketing to attract a crowd; understandable; correlate to their day-to-day problems"

Founder gave two rounds of landing direction: first "enterprise-grade, what LLMs
can't do, why companies adopt"; then the CORRECTION — "understandable by people,
correlate to their actual day-to-day problems." Synthesis (my honest read, founder
"proceed"): LEAD with the human problem in plain words; the enterprise/deterministic
strengths become the "why you can trust it" layer, not the headline. SHIPPED on
branch `landing-relatable` off main: (1) hero sub-line re-toned to lead with the
BENEFIT — "Point us at your usage and get a plain-English report: exactly where
every dollar goes, the specific waste you're paying for, and the fix for each" +
"your prompts never leave your stack" (was the mechanism-first "pulls/audits/
watches"). (2) NEW **"Sound familiar?" section** (.land-pain/.pain-grid, 6 relatable
one-liner pains in the customer's own words — "the bill jumped and no one can say
what changed", "we send the same giant prompt thousands of times at full price",
"one feature is quietly eating the budget", etc., each with a plain response). CSS
mirrors the .statcard token grammar (role tokens, hex-free). HONESTY held: the
attributed stats (79/31/98%) stay; pain lines are illustrative quotes, not claimed
stats; every capability claim is true (8 detectors, caching, breakdown, alerts,
counts-only). Landing laws intact: exactly ONE class="cta" (verified), five
providers still named, screenshots labeled sample data, budgets (<300KB total).
Independent of PR #19 (tokenomics) — different files. Tests: test_landing_budgets +
test_design_tokens (hex-free) + test_journeys all green. ux gate + PR next. NOTE:
this is a fully-editorial slice; FR-23 row (web/templates/landing) already covers it.
## TOKENOMICS BREAKDOWN — enterprise depth engine slice 1 (2026-07-25) — founder "enterprise-ready, industry-standard, deterministic, no LLM in the money path"

SHIPPED-TO-MAIN first: D8/D9 richer-findings merged as PR #18 (squash 2797081,
all gates PASS + CI green). Then a strategic thread: founder asked "should we have
our own trained model / LLM for analysis?" — ruled (my honest counter, founder
agreed): NO neural/LLM model — it burns tokens, is non-reproducible, can't be
100% precise on dollars, and FR-22 leaves no text to read anyway; the MOAT is the
DETERMINISTIC precision engine (exact, reproducible, private, reconciles to the
invoice) which an LLM tool cannot match. Founder chose (AskUserQuestion) the
"deterministic depth engine", first slice "usage/tokenomics breakdown", then
"enterprise-ready, not POC, abundant + granular + industry-standard". SHIPPED on
branch `tokenomics-breakdown` off main: **services/dashboard/tokenomics.compute** —
a PURE, deterministic breakdown of a priced frame: vitals (spend, tokens
in/out/cached, cache-hit rate, output:input, cost/1k-out, cost/request), per-model
+ per-route (tag = cost-allocation/showback) Slices, unit economics, and data
coverage (%priced/%attributed — untagged spend is its own row, never silently
allocated). Every figure is an exact sum/ratio of the coster's cost_usd — NOT a new
estimator, so no rate golden owed, but pinned by tests/test_tokenomics.py against
hand-derived values. **Runner** writes the tokenomics.json ARTIFACT at audit time
from the per-request frame (which purges later per FR-21 — computed once, same
pattern as spend_by_model). **GET /breakdown** reads the latest audit's artifact
(honest empty / unpriced-clarity state when absent); **breakdown.html**
(kit-composed stat tiles + `.ledger` tables); **Breakdown** nav in the Monitor
group + help_registry destination. The enterprise MOCKUP (docs/design/mockups/
tokenomics-breakdown.html) was ux-gated PASS-WITH-NOTES (all 3 actioned) + founder
"wire slice 1 as shown"; it also shows the NEXT slices — forecast/run-rate (slice
2, reuses existing metrics.forecast), statistical anomaly detection (slice 3),
optimization what-ifs (slice 4), export/API completeness (slice 5) — all
deterministic. X-02 respected: budget is a display reference for variance only,
never enforcement. File-map delta: +services/dashboard/tokenomics.py;
+templates/app/breakdown.html; runner writes tokenomics.json; +GET /breakdown;
+shell Breakdown nav; +help_registry breakdown destination; +tests/test_tokenomics.py
+tests/test_breakdown.py; +mockup; traceability row.

GATE ROUND: spec-guard PASS (X-01/X-02 read-only + budget display-only, FR-22
counts-only, T-NFR-01 pure, no golden owed, traceability) · cold PASS-WITH-NOTES ·
ux PASS-WITH-NOTES · vv money-CONFIRMED (golden re-derived; suite-green by my
un-piped runs) · system-tester PASS-WITH-NOTES (journey/reachability/seams
confirmed). Notes ALL actioned: (cold f.1) /breakdown now guards json.loads
(JSONDecodeError/OSError → honest empty state, never 500) AND the runner writes
tokenomics.json ATOMICALLY (temp + os.replace) so a concurrent read never sees a
partial file — pinned by test_corrupt_artifact_degrades_to_empty_state_not_500.
(cold f.2) attribution is now SPEND-weighted (Σ tagged cost / total, not row-count)
— the meaningful cost-allocation metric; "priced" renamed "Requests priced" (honest
— unpriced $ is unknowable); pinned by test_untagged_spend_lowers_attribution_by_
dollars_not_count. (ux f.4) the page now LEADS with a plain-English sentence bearing
the headline $/mo (R-PERSONA §5). (system-tester gap) added a cross-surface test
that the breakdown's monthly spend equals the ReportModel's. Full suite green; PR
next (holding merge for founder). One process slip owned: two gate agents (vv,
system-tester) hit their tool budget and one earlier gate committed mid-run — the
non-determinism/[[never-mask-pytest-exit]] discipline; the suite-green rests on my
own un-piped runs, not a masked agent invocation.

## RICHER FINDINGS — D8/D9 detectors (2026-07-25) — founder "many findings / dynamic analysis", chose "richer findings / more detectors"

SHIPPED-TO-MAIN first: the guided-first-run slice merged as PR #17 (squash
e74fa01; all gates PASS/PASS-WITH-NOTES + CI green; prod deploy stays
founder-gated). Then, on branch `richer-findings` off main, the founder's
"why so few findings" thread turned into two new detectors (AskUserQuestion: A +
D). Cross-provider arbitrage was DROPPED after checking the rate card — bedrock/
azure mirror anthropic/openai at parity, so no arbitrage exists. SHIPPED:
**D8 spend concentration** (informational "start here", like d5: flags a route
carrying >= d8_concentration_min_share (default 50%) of total spend, only across
2+ NAMED routes so a single-route log is never trivially flagged; $0 impact — a
pointer, never a claimed saving). **D9 ineffective cache** (cache is WRITTEN but
rarely READ → you pay the write premium without the read discount, so caching NET
COSTS you; money-math on the ACTUAL billed cache_write/cached tokens so
CONSERVATIVE not estimated; golden net_loss 0.3075 derived in
pricing_golden_NOTES.md D9 section per CLAUDE.md rule 4). KEY money-math property:
D9 is DISJOINT from D2 by construction — D2's eligible filter already requires
`cache_write_tokens == 0`, so no ROW is counted by both and the DOLLARS can NEVER
double-count, no D2 change needed (cold-review precision: a route CAN surface in
both a D2 and a D9 finding when it mixes never-cached and cache-written calls —
the savings amounts still never overlap). Both detectors are per-request-only
(added to aggregate.INACTIVE_ON_AGGREGATE: D8 needs route tags, D9 needs
cache_write counts that provider usage-API aggregates don't carry) — so they
enrich exactly the deep upload/SDK path the founder made primary. Both surface
through the existing finding UI (plain-English summary + technical pointers). They
do NOT fire on the committed waste_pack sample (checked), so the sample count +
report goldens are unchanged. File-map delta: +services/rules/d8_spend_concentration.py
+d9_ineffective_cache.py; registry DETECTORS (+2); aggregate INACTIVE (+2); config
d8_concentration_min_share/d9_min_cache_write_tokens; help_registry (+2 entries with
summary); help._threshold_values (+2); tests/test_rules.py (+TestD8/+TestD9 goldens)
+ registry-order/detector-count(6→8)/aggregate-coverage(6→8) updated; NOTES D9
derivation; traceability row. "More detectors beyond these two" stays a
founder-chosen follow-up (BACKLOG). Gate round + PR next.

## GUIDED FIRST RUN + OUTPUT PREVIEW (2026-07-25) — founder walkthrough punch-list #4/#5, "proceed guided-first-run"

The first-run vertical (R-VERTICAL), on a branch off main. GOAL: a brand-new
user (signed in, no source, no audit) met a grid of EMPTY widgets ($0.00, "No data
yet") + a checklist + a tour — the product read as empty and they had to connect on
faith. Now, ONLY in the true first-run state (no completed audit), that grid is
replaced by (a) a GUIDED "start here" hero — the connect→audit→report arc as three
steps, step 1 lit "YOU ARE HERE", both CTAs live (/upload, /sources) — and (b) an
OUTPUT PREVIEW of REAL sample-engine output so they SEE the value before connecting.
SHIPPED: **sample.sample_model** (memoised ReportModel — the FR-16 sample exposed
structurally, no WeasyPrint); **metrics.first_run_preview** (headline savings/%/spend
+ impact-ranked top-4 findings, $0 rows excluded but honest n_findings kept;
detector→plain mapped at RENDER via the help registry so the engine stays
presentation-blind); **routes_dashboard**: first_run = `latest_audit is None`, the
preview assembled only then and FileNotFoundError-degrades to the hero alone (never a
500); **_first_run.html** (guided hero + SAMPLE-fenced preview composing the kit
.ledger — the SAME findings table the real dashboard renders); dashboard.html
first-run branch (pipeline spine always; hero+preview XOR the live grid); the
getting-started checklist is SUPPRESSED in first run (the hero is the single
next-action surface) and resumes after the first audit for review→apply→verify;
wa-design.css `.fr-*` (estimate-palette fence, role-tokens only). HONESTY is
load-bearing (the data-coherence lesson): the preview is fenced "SAMPLE — NOT YOUR
DATA / nothing on this card is yours", uses the estimate palette NEVER verified-green,
and VANISHES the moment a real audit completes so it never sits beside a user's own
figures. **Real app figures** (the AUTHORITATIVE reproduction via the app's own
construction — `get_settings()` reading .env + `PricingTable.load()`, per R-TOOLCHAIN):
$0.89/mo · 11.7% · 5 findings on the committed sample (top-4 shown: d3 $0.50, d2 $0.25,
d6 $0.10, d4 $0.05; d5 is $0.00). They are CONFIG- and rate-card-dependent — a hermetic
test env (`_env_file=None`) computes different numbers ($2.24/29.5%/6), which is why the
journey suite asserts the rendered page against `first_run_preview` LIVE, never a
hardcoded literal. The preview + public /sample read the same settings+table so in any
one deployment they can never disagree. PROCESS NOTES (mine): the ux gate on the
mockup (BEFORE wiring, R-DESIGN) returned PASS-WITH-NOTES — all 4 actioned (5-vs-4
findings coherence made explicit; money promoted to the display HERO; the one delight
named; ribbon flex-wrap). Wiring then tripped THREE shipped laws the mockup's bespoke
HTML didn't: the kit table-composition law (hand-rolled `<table>` → kit.table_open),
the retired-serif law (R-LOOK-FINAL — `var(--serif)` banned → heavy sans for money
prominence), and the CSS `served==source` parity test (edit design/ then cp to
static). Test collateral fixed WITHOUT weakening intent (widgets that only render past
first run get a completed-audit seed): test_dashboard zero-state + test_onboarding
checklist (suppressed→resumes) + the verified-savings celebration + the daily-loop
"Yesterday" tile (in production a connected source triggers an audit per
R-LIVE-AUDIT, so daily data and a completed audit always coexist). Journey suite tests/test_guided_first_run.py green;
HTML-escaping (`&#39;`) + line-wrap were assertion bugs, fixed by whitespace-normalize
+ escape. File-map delta: +services/report/sample.sample_model;
+metrics.first_run_preview; +templates/app/_first_run.html; +wa-design.css `.fr-*`
(both copies); routes_dashboard passes first_run+preview; dashboard.html branch;
+tests/test_guided_first_run.py; +mockup guided-first-run.html; +traceability row. No
pricing/estimator touch → CLAUDE.md rule 4 N/A. DEPENDS-DONE: O-1 stack (main).

REV 2 (founder walkthrough on PR #17, 2026-07-25 — "not approved… connecting
sources is the main feature but upload was highlighted… Findings/Report must be
plain human english, a proper summary; each finding looks too complicated"):
mockup NOT approved → revised + re-approved (AskUserQuestion: "wire it as shown",
scope = "technical pointers ALONG WITH the plain-English summary, for both
technical and common man"). SHIPPED on the same branch: (1) **First-run CTA
emphasis.** Founder first said "connect is the main feature"; a follow-up ("why so
few findings — can be many, dynamic analysis") surfaced the DEPTH mechanic and
REVERSED it (AskUserQuestion "Upload/SDK primary (depth)"): per-request logs
(upload/SDK) run all SIX detectors PER ROUTE → the most findings, so **Upload a log
is the PRIMARY action** (btn-primary → /upload); connecting a provider is the
SECONDARY automatic-daily path — provider usage APIs give only coarse day×model
aggregates so just 3 of 6 detectors run and it finds less (aggregate.py
INACTIVE_ON_AGGREGATE). The trade is stated honestly on the hero. "More detectors /
richer per-route analysis" = a founder-chosen FOLLOW-UP, not this slice. (2)
**Plain-English finding summaries** — a new `summary` field per detector in
help_registry.yaml (common-man "what's happening + why it costs"; NO jargon/
thresholds) + DetectorHelp.summary + help.detector_summary() + i18n
kit.finding.summary "In plain English". Every finding now LEADS with the plain
summary and KEEPS the technical pointers (detector id, thresholds, evidence) —
both audiences, plain-first: finding **drawer** (summary prepended above the
unchanged depth-c why→evidence→fix→verify, so R-CLARITY order + R-PERSONA jargon
tests still hold), **Findings page** (summary sub-line under each title), **dashboard
top-findings** widget, and the **first-run preview** (now plain-English cards:
title + human summary + $, replacing the kit ledger — no table, so the kit-table
law is N/A). Detector→summary mapped at render via the registry (engine stays
presentation-blind). SCOPE CARVE-OUT (transparent): the downloadable **PDF report**
is render-only + services-layer (render_report_html passes only the ReportModel,
no help access), so plain-English there needs the detector copy moved to a
services-accessible source — the explicit FAST-FOLLOW, not hacked in via a
layering break. Tests: connect-is-primary CTA, preview shows every finding's plain
title AND summary, drawer has "In plain English" leading + technical pointers still
present. File-map delta (rev 2): +help.detector_summary + DetectorHelp.summary;
+summary in 6 detector entries; +i18n kit.finding.summary; drawer/findings/
top_findings/first_run templates lead with summary; +wa-design.css .finding-plain/
.finding-sub/.fr-find* (both copies). Gate round + PR update next.

## DATA COHERENCE + HONEST FRESHNESS (2026-07-24) — founder walkthrough: "no sources connected but overview/findings show old cache data, not real-time"

Founder prod walkthrough (v1.9.0 = O-0) surfaced an HONESTY gap, not a cache bug:
there is NO server cache — the mechanism is that the Sources page hides revoked
sources (`status != 'revoked'`) while audits + their findings PERSIST, and
Overview/Findings scope to the same workspace and keep rendering the last audit's
real numbers. So "nothing connected" sits next to live-looking figures with no
signal they are HISTORY. (X-01 means we're batch-audit, never a live proxy — data
is legitimately as-of-last-audit; the fix is to SAY so, coherently.) Founder chose
(AskUserQuestion) this fix FIRST, seen on prod → the revoked/absent-sources case.

SHIPPED (vertical, R-VERTICAL): **metrics.has_live_feed(session, user_id)** — True
iff the active workspace has an active Source OR an unrevoked IngestKey OR an
unrevoked Device (mirrors exactly what "connected" means on the Sources page).
**shell.data_freshness(session, user_id)** — the shared seam (the workspace_bar
pattern): returns `freshness`, `sources_disconnected`, `data_as_of`; when a past
audit exists but has_live_feed is False, `sources_disconnected` flips True and the
freshness line gains "· nothing connected". Wired into BOTH `_shell_ctx` (the 8
pages: dashboard/runs/settings/alerts/statements/explore/billing/members) AND the
4 manual-render full pages (sources, connect wizard, developer, upload) — the same
5 sites workspace_bar uses, so coverage is every shell page (the `_`-prefixed
htmx partials don't render the shell). **Shell banner** (_shell.html, after the
purpose line → on EVERY app page): when `sources_disconnected`, an honest
`.since-here` notice — "Nothing is connected to bring in new usage right now — the
figures here are from your last audit on <date> and won't change until you
reconnect" + a "Connect a source" CTA. So "no sources connected" (Sources) can
never again sit beside numbers that read as live. tests/test_data_coherence.py: 4
green (healthy → no banner + live freshness; revoked-all → banner on dashboard +
sources + runs, both _shell_ctx and manual paths, freshness flags it; new user no
audit → honest "No data yet", no banner; a live ingest key counts as connected).
ruff+mypy clean; dashboard/sources/spine/developer suites green.

GATE ROUND CLOSED — cold PASS-WITH-NOTES · ux PASS-WITH-NOTES · system-tester
PASS-WITH-NOTES; none FAIL, no live bug. ALL notes applied: **ux f.4** — the
banner fired on account pages (settings/billing/members) with no figures to
contextualize → SCOPED to figure pages only (overview/runs/statements/explore/
findings/alerts/activity) via a template allowlist; the terse "· nothing
connected" topbar marker still carries the honesty on every page. **ux f.5** —
`.since-here` had no flex-wrap and the coherence copy is the longest such banner →
added flex-wrap + `min-width:0` on the span (both CSS copies kept in lockstep per
the design-asset parity test). **system-tester f.4** (the real catch) — the
`/audits/{id}/progress` theater is a shell page that bypassed _shell_ctx AND the
manual seam, so it hardcoded `freshness=""` and silently disagreed (it also lacked
the O-1b-1 workspace bar) → wired BOTH `workspace_bar` + `data_freshness` into it,
+ a test that pins the freshness marker there (banner stays off — single-audit
view). **cold f.1** — the Device OR-arm of has_live_feed was untested → added a
live-Device test. **cold f.3** — the anonymous sources path relied on Jinja's
silent Undefined → explicit `{sources_disconnected:False,…}` defaults. **cold
f.4** — 'paused' source status is forward debt (never assigned today) → design
comment + BACKLOG line for R-Q6. Banner copy also broadened to "connect a source
or upload a new log" (upload-only users have no source to reconnect).
tests/test_data_coherence.py now 6 green (healthy→none; disconnected→banner on
figure pages + marker everywhere + ABSENT on settings/sources; audit_progress
carries the marker; live Device/IngestKey→connected; new user→No data yet).
ruff+mypy clean. system-tester RE-GATE PASS (both fixes confirmed live, 78 passed,
no regression, no new issue). Slice DONE — ready for PR.
(Broader founder punch-list #3–#7 — Claude-style docs, step-by-step client & dev
onboarding, Developer-surface clarity, "feel like magic" + more functionalities —
captured as the next themes, founder to sequence.)
## O-1b-3 MEMBERS PAGE & REVOKE (2026-07-24) — founder "proceed O-1b-3"

The governance slice that CLOSES O-1b, built end-to-end (R-VERTICAL) on a branch
off main. GOAL: an owner sees who is in the workspace and can remove them; a
removed member loses access. SHIPPED: **repo.list_workspace_members** (the
inverse of list_memberships — the users IN one workspace, joined to User for the
email, owner-first then joined; every row has a real user). **Members page
roster** — GET /settings/members now renders email · role · joined, VISIBLE TO
EVERY MEMBER (you should know who you share a workspace with), with a per-member
**Remove** control that renders ONLY for an owner over a NON-owner (`can_revoke`):
a plain member sees the roster with NO revoke/invite control AT ALL — absent, not
a 403 they bump into (the reachability law for permissions, foreshadowing O-2) —
plus the honest "just you so far" solo empty state. **POST
/settings/members/{id}/revoke** (OWNER-ONLY) deletes the WorkspaceMember — and
that is the WHOLE mechanism: the switchable `active_workspace_id` resolver already
falls a revoked member back to their PERSONAL workspace on their very next
request, so access stops with no extra step (pinned by the journey test). Guards,
fail-closed: owner-of-THIS-workspace only; the target must be a member OF this
workspace else 404 (a guessed/foreign member id can never reach across tenants);
the OWNER row is never revocable → 400 (a workspace always keeps its owner, which
also blocks an owner orphaning their own workspace). **Invite governance**: POST
.../invite/{id}/resend (owner + Scale + rate-limited 5/min; RE-MINTS the code,
overwriting the stored hash so the previous link dies instantly — a rotation,
never a second live code) and POST .../invite/{id}/cancel (owner-only, no Scale
gate — cleanup is always allowed; deletes the pending invite so its link loads
nothing → the same honest 'invalid' state). All mutations owner-scoped fail-closed
(member-level RBAC still belongs to O-2). tests/test_workspace_members.py: 8 green
(roster→revoke→access-stops with resolver fallback; revoke control absent for a
member AND route owner-only; owner row 400; foreign id 404; solo empty state;
resend rotates + old link dies; cancel withdraws + kills link; resend/cancel
owner-only). ruff+mypy clean; workspace suites green. Traceability O-1b-3 row
added.

GATE ROUND CLOSED — spec PASS-WITH-NOTES · ux PASS-WITH-NOTES · cold
PASS-WITH-NOTES · system-tester PASS; none FAIL. spec's only note (the new test
file was untracked → invisible to `git diff main`) resolved by `git add`. cold
caught two REAL issues, both FIXED: **f.1** — the roster `order_by(role)` sorted
ascending so "member" (m) preceded "owner" (o), listing members ABOVE the owner
and contradicting the "owner-first" claim; replaced with an explicit
`case(role=='owner' → 0)` key (future-proof vs O-2's admin/viewer) + a regression
test pinning owner-row position. **f.2** — resend rotated the stored hash (killing
the old link) BEFORE the mail send, so a failed resend stranded the invitee with
no working link under a banner that only said "try again"; reordered to
send-BEFORE-rotate so a failed resend leaves the EXISTING link intact, with a
distinct `resend-failed` banner ("the previous link still works") + a test that
makes the adapter raise and asserts the old code still accepts. cold f.3 (INNER
join would silently drop a member if an account-delete path is ever added) →
comment caveat; f.4 (assert-vs-HTTP for the ws invariant) → pre-existing pattern,
no change. ux's three kit-conformance notes all APPLIED: roster + pending-invites
lists converted from hand-rolled `<ul>` to `kit.table_open/close` (labeled
columns, the Datadog/Stripe row grammar), the solo state now uses
`kit.empty_state`, mobile crowding resolved by the table treatment. system-tester
walked the governance journey LIVE (revoke → the fallback is observable on the
dashboard, a second surface, not merely DB-true; owner-only surface absent-not-403;
resend/cancel functional; no regressions) with zero product findings.

COLD RE-GATE (fix diff) PASS-WITH-NOTES — both fixes CONFIRMED correct, no
regressions. Two re-gate notes, both ADDRESSED: (2) the owner-first test was weak
— the owner's membership seeds BEFORE the member's, so `created_at` alone already
ordered owner-first and the test would pass even with the `case` key deleted →
STRENGTHENED: the member's join is now backdated a day BEFORE the owner's, so
owner-first can hold ONLY if the explicit `case` key beats chronology (the test
now fails if the key is dropped for a bare `created_at` sort). (4) resend held the
DB session across the mail call (unlike invite_member, which sends outside it) — a
latent pool risk with the real SMTP adapter → RESTRUCTURED to three phases:
authorize+read (session closed), send with NO session held, then reopen to commit
the rotation (re-checking the invite is still pending — skips silently if it was
accepted/canceled during the send). Mail is now out of the transaction, matching
the sibling route; the send-before-rotate guarantee cold already confirmed is
preserved (a failed send still leaves the old link live). Self-reviewed rather
than spawning a third cold pass — the change is localized and covered both paths
(rotate-on-success + failure-leaves-old-link). ruff+mypy clean project-wide;
workspace suites green (members 10 + invites 7). NEXT: full suite → commit → PR →
merge → O-1 CLOSES.

## PUBLISHED + O-1/LE-1 MERGED TO MAIN (2026-07-24) — founder "publish ... merge and squash", then "ownership/clarity/eliminate cognitive debt"

The repo is LIVE (github.com/delvinggeeks/tokenops-cost-auditor, private) and `main`
now holds, CI-GREEN (all jobs: authorship·lint·type·docs·test·build; verified on
GitHub AND a full local run), the entire O-1 tenancy layer (foundation + read
re-scope sweep + members backend) + LE-1 (authorship hard gate) + PLATFORM.md.
Fast-forwarded (clean commit story preserved, not squashed to one blob — founder
may request a flatten). Merged branches deleted; `le-2-continuous-deploy` (PR #6)
HELD — merging it arms auto-deploy-to-prod and needs DEPLOY_HOST/DOMAIN/SSH_KEY +
one validated run; `main`'s deploy.yml stays dispatch-only so nothing auto-shipped.

THE FIRST-EVER CI RUN + a cold-review caught THREE latent, non-leak issues, each
fixed before merge (the loop's containment working, exactly the cognitive-debt
concern): (1) obs/sentry-sdk optional extra not installed in CI → 1/876 test fail
→ ci.yml now `uv sync --frozen --all-extras`; (2) endpoints.md 735 lines stale
since S-6 → regenerated; (3) an N+1 I reintroduced in the O-1b billing re-scope →
batched via subscriptions._active_workspace_ids (+ deterministic _subs_by_workspace
ORDER BY, migration-invariant comment) — cold PWN, no leak. Plus a ruff-FORMAT gap
in routes_dashboard.py the first partial-local checks missed. LESSON: run the EXACT
full CI commands locally, never partial — that gap is the cognitive-debt surface.

STRATEGIC (founder ownership/clarity ruling): PLATFORM.md is the one-page
ownership map (architecture · tenant-blind engine boundary · module map · tenancy
· methods · tools · docs index · §8 cognitive-debt model). Loop model refined to
COMPREHENSION-PRESERVING autonomy: fully autonomous for routine slices, a
comprehension checkpoint on the load-bearing few (migrations, engine, money,
tenancy). See [[loop-engineering-model]], PLAN-LOOP-ENGINEERING.md.

NEXT (each a fresh focused session per K-3/TE-9 — the recommended discipline):
FOUNDER-LANE: set 3 deploy secrets → un-hold LE-2; branch protection (main
green-only). LOOP: LE-3 auto-merge → LE-4 gate-agents-in-CI → LE-5 autonomous
driver. PRODUCT: O-1b-1 workspace switcher → O-1b-2 invite&accept → O-1b-3
members page&revoke (full specs in PLAN-ORG §O-1). Start any with "proceed <id>".

## DEVOPS CYCLE ACTIVATED (2026-07-24) — founder "why no PR ... proper devops cycle?"

Root cause: the repo was LOCAL-ONLY (no git remote) — `gh pr`/GitHub Actions had
nothing to run against, so O-1 accumulated on one branch (wp-report-explorer) with
gate AGENTS as the local CI equivalent. gh is now authed (delvinggeeks, repo+
workflow). Founder decisions (AskUserQuestion): (a) **founder** does the publish
(create+push repo) — agent prepped branches/PR bodies/commands (scratchpad
activate-github.sh); (b) split the done O-1 work into **separate stacked PRs**.
Branches cut per concern off main: `o1a-read-rescope` (d7a5c43+f547d33, fully
gated) → `o1b-members-backend` (d52960e; automated-green, agent gate round
RECOMMENDED before merge) → `o1b-slice-plan` (docs). Merge order PR1→PR2→PR3.
Deploy secrets for deploy.yml: DEPLOY_HOST/DEPLOY_DOMAIN/DEPLOY_SSH_KEY (ci.yml
needs none).

GO-FORWARD (every session from O-1b-1 on): work on a branch OFF MAIN → push (ci.yml
runs ruff/mypy/pytest+coverage+pricing-verify/docs-drift) → open a PR (template) →
run the agent gate round + paste TE-8 verdicts in the PR → squash-merge to main
(branch protection: green PR only) → tag → deploy.yml (workflow_dispatch = the
founder's "approved to deploy") → smoke + auto-rollback. No more long-lived
catch-all branches; one slice = one branch = one PR.

## O-1b BACKEND FOUNDATION (2026-07-24) — founder "Approved go with the recommendations"

Founder RULED PLAN-ORG Q3: **one subscription per workspace, members INHERIT the
plan; billing VISIBILITY is role-gated in O-2** (recorded in auto-memory
[[workspace-billing-model]]). Built the members backend — all BEHAVIOR-PRESERVING
under 1:1 (nothing activates until an invite creates a second member), so it is a
safe checkpoint on the branch; the member-facing VERTICAL (invite UI → journey)
completes O-1b before any merge/deploy (R-VERTICAL).

SHIPPED: **migration 021** (rehearsed upgrade+backfill+downgrade on throwaway
sqlite w/ pre-existing data) — `users.active_workspace_id` (backfilled to the
personal workspace), **workspace_invites** (invite by email, one-shot HASHED code
= the LinkCode grammar, email-match on accept), and `workspace_id` on
**alert_events + alert_checks** (backfilled; PAYMENTS deliberately EXCLUDED —
billing visibility is O-2). **Switchable resolver**: repo.active_workspace_id now
returns `User.active_workspace_id` IF the caller still holds a live membership in
it, else the personal workspace — two leak-safety guarantees pinned: (1) the
returned workspace is ALWAYS one the caller is a member of (a revoked/stale/
foreign pointer silently falls back — a switch can't become a privilege grant),
(2) never None for a real user. Added repo.set_active_workspace (validates
membership) + repo.list_memberships. **Billing re-scope** (the O-1a deferral,
now ruled): entitlements/entitlements_for/viewer_currency read the ACTIVE
workspace's subscription (members inherit); new entitlements_from_workspace +
entitlements_for_workspaces; the scheduler keys on the SOURCE's workspace (not
the owner's active one); apply_event stays payer-keyed (owner==workspace 1:1 in
O-1b). **Member-visibility**: AlertEvent/AlertCheck DISPLAY reads (activity feed,
/runs ledger, alerts history) flip to workspace + their WRITES stamp workspace_id;
per-recipient dedup stays user-scoped; Payment stays user-scoped (O-2). conftest
fixture-stamp hook extended to AlertEvent/AlertCheck. ruff+mypy clean; affected
suites green.

REMAINING for O-1b is now SPLIT into three fresh-session vertical slices, each
with acceptance criteria + DoD, in PLAN-ORG.md §O-1 (founder 2026-07-24): **O-1b-1
workspace switcher** (navigation spine), **O-1b-2 invite & accept** (the core
grow-the-workspace journey), **O-1b-3 members page & revoke** (governance). Start
a fresh session per slice ("proceed O-1b-1", etc.); PLAN-ORG carries the full
spec. Original remaining-work notes (superseded by the split, kept for detail):
invite backend (POST /settings/members/invite,
owner-only, TEAM/"Scale"-plan-gated — that plan was SOLD as multi-seat and O-1b
is what lets it deliver; rate-limited; emailed accept link) + accept flow (email
match + atomic one-shot consume + add WorkspaceMember(role=member) + set active
workspace) + workspace SWITCH (POST, via repo.set_active_workspace) + revoke
membership (owner-only); the **Members page** UI (mockup-FIRST per ux gate: list
members/roles/joined, pending invites, invite form, revoke, switcher) reachable
from Settings nav; honest empty/error states; the **journey test** (invite →
accept → invitee reaches the shared dashboard + sees the owner's audits →
switch → revoke stops access) hardening isolation from 1:1 to multi-member; then
the gate round (ux, spec, cold, system-tester) + STATUS/traceability.

## O-1 SWEEP GATE ROUND CLOSED (2026-07-24) — cold PWN · spec PASS · vv PWN; sweep clear for O-1b

Three gates, none FAIL. cold-reviewer PASS-WITH-NOTES: **found NO missed site and
NO wrong flip** across the whole re-scoped set (the load-bearing result — misses
are invisible under 1:1, so this is the check the equivalence oracle cannot make);
confirmed the None/IS-NULL leak-safety and that the conftest hook is None-only
(cannot mask a production stamp). f.4 (create-source mutate reads lacked a LOCAL
justification comment — only user_plan's docstring covered them) FIXED: one-line
O-1 comments added at routes_sources.py create-gates (153/267/531 clusters). f.5
(metrics.pipeline re-resolves active_workspace_id per delegate) ACCEPTED with
reason — a deliberate consequence of the "signatures unchanged, resolve
internally" execution decision; deterministic, same session/user, indexed scalar;
threading ws through delegate signatures is the thing that decision avoided.
spec-guard PASS: engine stays tenant-blind (services/rules+pricing untouched,
T-NFR-01 holds), X-01/X-02 intact (no proxy/enforcement), FR-22 clean (no text),
every deferral has a named home (not a silent drop), traceability O-1 row
accurate. vv-engineer PASS-WITH-NOTES: money-math untouched (pricing/rules diff
empty, _rate_cost byte-identical, no goldens needed), new isolation tests assert
real cross-tenant isolation, conftest hook doesn't neuter TestWritePathStamps;
its one open item — it couldn't reproduce the green suite inside its own tool
budget — is closed by the main thread's independently-confirmed run (uv run
pytest exit 0, all green). SWEEP is COMPLETE + grep-audited + cold-gated → the
STATUS bar for starting O-1b MEMBERS is met.

## O-1 SWEEP DONE — reads re-scoped to workspace_id (2026-07-24) — founder "proceed with O-1"

The read re-scope, done in a fresh session (K-3/TE-9) as chosen. Measured live:
87 sites via `grep .user_id ==`, PLUS a whole CLASS the O-1-STARTED inventory
MISSED — `.user_id !=` ownership guards and repo.get_user_audit's EMAIL check
(re-swept comprehensively; lesson: a `==`-only grep under-counts tenant scoping).

CHOKEPOINT: repo.active_workspace_id. Every DISPLAY read now resolves
`ws = active_workspace_id(session, user_id)` and filters `X.workspace_id == ws`
(signatures unchanged, internal resolution per the O-1-STARTED decision; no
global query filter). HARDENED active_workspace_id to ensure-create so it NEVER
returns None for a real user — else `workspace_id == None` renders IS NULL and
matches every tenant's un-stamped rows (THE load-bearing leak vector; pinned by
test).

TRIAGE (a comment at EVERY survivor states intent, so the gate reads deliberate
not missed). FLIPPED→workspace: the 10 owned tables' display reads (Audit,
Source, IngestKey, ApiToken, OAuthApp, Device, AlertRule, Statement — SavedView
& Subscription excepted, below) + children via a workspace-owned parent
(SourceUsage→Source, FindingFeedback→Audit) + get_user_audit + the S-6 read
tokens (routes_api_read/api_auth → the token-owner's active workspace). STAYED
user_id, each leak-safe and NONE a miss: membership/idempotency/magic-link
(identity); AlertEvent/AlertCheck/Payment (NO workspace_id column — O-1b);
Subscription/entitlements/currency (member plan-inheritance is UNRULED, PLAN-ORG
Q3 → O-1b/O-2); SavedView + developer tokens/OAuth-app management (personal by
per-user uq + design); admin (cross-tenant superuser by design); and EVERY
mutate-select — revoke/rename/purge/close-account/mint/feedback/save-rules —
fail-closed until O-2 RBAC (a member SEES the workspace, cannot yet CHANGE it).
No migration (O-0 added + backfilled the columns).

SAFETY NET, all three run: (1) full regression as the 1:1 equivalence oracle —
it surfaced that ~19 test files build rows RAW (`User(email=…)`,
`Audit(user_id=…)`) with no workspace_id (invisible under workspace reads) AND a
3-4x slowdown (raw users had no workspace, so active_workspace_id hit
ensure-create on EVERY read). Fixed with ONE conftest before_flush PARITY hook:
raw fixtures get workspace_id stamped + raw users a workspace-of-one, exactly as
production's create-sites do. It is None-ONLY, so it can NEVER hide a missing
production stamp — create_audit et al. set a real value and stay tested by
TestWritePathStamps. (One test, test_runs::test_13, reassigned .user_id after a
flush → stale workspace_id; fixed in-test to carry the workspace.) (2) the
comprehensive grep-audit — every surviving `.user_id ==/!=` justified + commented.
(3) new tests test_workspace_spine.TestReadScopeSweep (ensure-create/never-None,
get_user_audit workspace scope, NULL-workspace never leaks, service read
isolates); the existing read-API two-tenant test now exercises the workspace
path. Whole suite green; ruff+mypy clean. Traceability O-1 row added.

FILE MAP DELTA: repo.active_workspace_id hardened + get_user_audit re-scoped;
~18 service/route modules flip display reads (import active_workspace_id);
tests/conftest gains the fixture-stamp hook; tests/test_workspace_spine +4.

NEXT: cold-reviewer gate hunting MISSED sites (the invisible-under-1:1 risk),
then O-1b MEMBERS — invite (hashed one-shot code, link-code grammar), member
joins, Members page, workspace SWITCH (this is what makes active_workspace_id
SWITCHABLE), revoke — plus the enablers this sweep PARKED: AlertEvent/AlertCheck/
Payment workspace_id + member visibility (activity-feed coherence), the billing
model (Q3), and the O-2 RBAC that gates the mutate-selects now fail-closed.

## O-1 STARTED — FOUNDATION ONLY (2026-07-24) — founder "proceed with O-1" → "Fresh session" for the sweep

O-1 (members + invites + the read re-scope). Measured the first task precisely:
the read re-scope is **89 `user_id`/`owner_user_id` filter sites** (plan said
"40+"), atomic (can't ship half — a member would see an inconsistent mix), and
the highest-blast-radius change in the codebase (a MISSED site = cross-tenant
leak once a workspace has 2+ members). Founder chose (AskUserQuestion) to do the
sweep in a FRESH session (K-3/TE-9). This commit ships ONLY the foundation —
NOTHING is re-scoped yet, so the tree is behavior-preserving and safe.

SHIPPED: `repo.active_workspace_id(session, user_id)` — the single READ-scope
chokepoint. O-1a returns the user's PERSONAL workspace (== workspace_id_for), so
flipping a read from `X.user_id == user_id` to `X.workspace_id ==
active_workspace_id(...)` is behavior-preserving while 1 user = 1 workspace.
O-1b makes it the SWITCHABLE active workspace (validated vs the caller's
memberships) — recommend storing the active workspace as `User.active_workspace_id`
(server-side, simplest; migration 021) or a signed cookie. Test pins the O-1a
contract (test_workspace_spine.py TestActiveWorkspaceResolver, 12 green).

EXECUTION DECISION (internal-resolution, LOWEST RISK): keep every read
function's `(session, user_id, ...)` SIGNATURE unchanged (zero caller churn), and
INSIDE each read resolve `ws = active_workspace_id(session, user_id)` + change the
filter COLUMN user_id→workspace_id. Delegates (metrics→compute/daily/forecast)
each resolve the same ws from the same user_id → consistent. Do NOT use a global
SQLAlchemy query filter (magic, hard to review, engine must stay tenant-blind).

THE 89-SITE INVENTORY (grep `\.user_id ==|\.owner_user_id ==`), by file — the
fresh session's work-list. TRIAGE each: most are READS to re-scope; some are
WRITES (already stamp workspace_id, leave) or legit per-USER lookups (e.g. a
user's own membership, magic-link) that STAY user_id:
  services/dashboard/metrics.py:13, web/routes_sources.py:9,
  services/dashboard/activity.py:8, web/routes_runs.py:7, web/routes_settings.py:6,
  services/dashboard/explorer.py:5, web/routes_developer.py:4,
  services/statements/build.py:4, web/routes_statements.py:3,
  web/routes_explorer.py:3, web/routes_alerts.py:3, services/connectors/daily.py:3,
  services/alerts/rules.py:3, web/routes_admin.py:2, services/payments/subscriptions.py:2,
  services/payments/base.py:2, web/routes_ingest.py:1, web/routes_dashboard.py:1,
  web/routes_api_read.py:1, services/payments/plans.py:1, services/forecast.py:1,
  services/dashboard/savings.py:1, services/alerts/dispatch.py:1.

SAFETY NET for the sweep: (1) run the FULL regression suite after each subsystem
— under 1:1 it is a complete equivalence oracle, so any WRONG re-scope breaks a
journey; (2) after the sweep, grep for remaining `user_id ==` in read paths —
each survivor must be justified (write/dedup/per-user), this catches MISSED
sites (invisible under 1:1); (3) a dedicated cold-reviewer gate hunting misses.
MEMBERS (O-1b: invite by email one-shot hashed code = link-code grammar, member
joins, Members page, workspace switch, revoke) does NOT ship until the sweep is
COMPLETE + grep-audited + cold-gated. NOTE the S-6 read tokens (rt_/at_ in
web/routes_api_read.py + api_auth) also flip to active-workspace scope here.

## O-0 DEPLOYED — v1.9.0 LIVE (2026-07-24) — founder "Deploy O-0 (v1.9.0), then O-1"

Pre-deploy backup OK. provision.sh --tag v1.9.0: migration 020 applied
(b7d34e9a1c60 → c8e05a1f6b20). BACKFILL LIVE-VERIFIED on prod: 7 users → 7
workspaces → 7 owner memberships; 0 users without a workspace; 0 users with 2+
owner workspaces; 10/10 audits stamped with workspace_id; uq_owner_membership_per_user
index present. Smoke: healthz {"ok":true}, landing OK, magic-link 200 (the
provision smoke-path fix now fires), docs 200. CHANGELOG v1.9.0 recorded. The
patched provisioner also (re)applied the SSH hardening. Next per founder: O-1
(members + invites + the 40-site read re-scope to workspace_id — O-0's deferred
half).

## O-0 GATE ROUND CLOSED (2026-07-24) — architect PWN · spec PASS · cold PWN · system-tester PWN · ux PWN

Five gates, none FAIL. spec PASS (R-ORG bounds, engine tenant-blind, deferral
documented). architect PWN (boundary/additivity/no-cycles confirmed; the note —
routes construct ORM directly — is PRE-EXISTING codebase debt, not O-0). cold
PWN → FIXED: (f.1) the workspace-of-one 1:1 invariant was not DB-enforced
(get_or_create_workspace was select-then-insert; uq_workspace_member covers
(workspace_id,user_id) not one-owner-per-user) → added a PARTIAL UNIQUE INDEX
uq_owner_membership_per_user (user_id WHERE role='owner', portable both backends)
+ made the helper race-safe (savepoint + catch IntegrityError + re-read winner);
(f.2) workspace_id_for docstring corrected. Migration 020 (UNSHIPPED — prod still
at 019, verified) edited in place to add the index; re-verified upgrade+backfill+
downgrade. ux PWN → FIXED: Workspace icon source→overview (was dup of Connected
sources), Rename button → kit.button. system-tester PWN: all O-0 journeys live-
green (rename A-changed/B-untouched, ingest isolation intact, no regression); its
finding 6 (no in-app link to /r/{token} — reports email-only, unlinked-Anthropic
class) is PRE-EXISTING + a separate surface → parked in BACKLOG as its own
reachability slice. New test: second owner membership rejected by the DB (proves
the 1:1 is now a fact). test_workspace_spine.py 11 green; ruff+mypy clean.
Next: DEPLOY O-0 (v1.9.0), then O-1.

## O-0 WORKSPACE SPINE (2026-07-24) — founder "proceed with O-0" + "Spine now, read-scope in O-1"

The tenancy root, R-ORG. Precisely scoped first: 17 owned tables, 40+ user_id
query sites. Founder chose (AskUserQuestion) "Spine now, read-scope in O-1" —
the safe path. Shipped: **Workspace + WorkspaceMember** models (owner membership),
**migration 020** (creates both tables + backfills a personal workspace-of-one
per existing user + stamps workspace_id 1:1 — verified upgrade+backfill+downgrade
on a throwaway sqlite with pre-existing data), **workspace_id** on the 10
directly-owned resource tables, **repo.get_or_create_workspace / workspace_id_for**
with get_or_create_user auto-creating the workspace-of-one and all 11 creation
sites stamping workspace_id, the **Settings → Workspace** surface (see + rename,
owner-only, audit-logged). Reads STAY user_id-scoped (correct while 1 user = 1
workspace → ZERO leak risk; O-0's DoD "B invisible to A" holds by the 1:1
invariant). The 40-site read re-scoping MOVES to O-1 (columns already exist +
backfilled, so no new migration; S-6 tokens flip to workspace scope there too).
ENGINE STAYS TENANT-BLIND: a grep-guard test asserts services/rules +
services/pricing never mention Workspace/workspace_id. tests/test_workspace_spine.py
10 green (creation, write-path stamp, ISOLATION, rename journey, tenant-blind
guard, ingest regression). ruff+mypy clean. Gate round next.

## PROD SECURITY AUDIT + SSH FIX (2026-07-24) — founder "hardening done, security etc?"

Audited the live host. HARDENED OK: ufw active (default-deny in, only 22/80/443),
app+postgres expose-only (not published — only Caddy binds 80/443), Caddy TLS
(Let's Encrypt live), fail2ban (sshd jail), .env chmod 600 root-only,
unattended-upgrades enabled. FOUND + FIXED one real gap: SSH still allowed
password auth AND root password login — the provision sed on /etc/ssh/sshd_config
was silently defeated by 50-cloud-init.conf ("PasswordAuthentication yes"),
because the Include sits at the top and sshd is FIRST-match-wins. Fixed live via
a 00-hardening.conf drop-in (sorts first → wins): PasswordAuthentication no,
PermitRootLogin prohibit-password, KbdInteractive no — validated with `sshd -t`
before reload, key auth preserved (fresh connection verified). provision.sh
harden step rewritten to do the same so future deploys don't regress (R-IMPROVISE).

## S-6 DEPLOYED — v1.8.0 LIVE (2026-07-24) — founder "deploy S-6, then O-0"

Founder chose (AskUserQuestion) deploy-first. Pre-deploy backup OK
(/backups/tokenops_2026-07-24.dump). `scripts/provision.sh --tag v1.8.0`:
image rebuilt, migrations 018 (ingest_keys — prod DB was still at 017, so S-0's
table was created NOW) AND 019 (developer platform) both applied transactionally
→ head b7d34e9a1c60. Smoke: healthz ok, landing ok, docs 200. LIVE-VERIFIED from
outside: GET /api/v1/audits no-token → 401 NFR-14 envelope; unknown OAuth client
→ on-site 400 with empty redirect (open-redirect guard); /oauth/token garbage →
invalid_client; all 4 S-6 tables present in prod. CHANGELOG v1.8.0 recorded.
FIXED in-slice (R-IMPROVISE): the deploy smoke probed /auth/magic-link (dead
→ 405) so its "magic link issued" check never fired — corrected to the real
/auth/signin-link in provision.sh; validates on the next deploy. Next: O-0.

## S-6 GATE ROUND CLOSED (2026-07-24) — spec PASS · ux PWN · cold PWN · system-tester PWN; all notes applied

Four gates, none FAIL. spec-guard PASS (FR-22 counts-only, X-01/X-02 hold,
engine tenant-blind, traceability accurate). cold-reviewer PWN, 3 findings all
fixed: (f.1) `with_for_update` is a no-op on SQLite so single-use could degrade
under concurrency → replaced with an ATOMIC conditional UPDATE (`WHERE
consumed_at IS NULL` + rowcount==1), correct on both backends; (f.2) `_pkce_ok`
raised UnicodeEncodeError on a non-ASCII verifier → guarded, now a clean
invalid_grant; (f.3) dead `OAuthAccessToken.revoked_at` implying an unbuilt
per-token revoke → removed from model + migration (app-revoke is the complete,
tested mechanism). ux PWN, both applied: OAuth panel icon settings→method (gear
collided with Settings nav), delight-declaration comments added to the two
reveals. system-tester PWN: reachability + plan-gating + API-token journey
walked green; its note that the OAuth test hand-constructed `decision=approve`
→ closed by scraping the real consent form (`name="decision" value="approve"`
asserted) + a dedicated consent-form-fields test. New regression tests: non-ASCII
verifier, consent-form DOM. test_developer_platform.py now 26 green; ruff+mypy
clean. Fixes committed on the same branch; milestone closed. Next: O-0.

## S-6 READ PLATFORM (2026-07-24) — read tokens + read API + OAuth server; founder "full S-6 incl OAuth apps"

Founder picked the FULL S-6 slice (AskUserQuestion): read-scoped API tokens,
the read endpoints, AND a full OAuth 2.0 authorization server, one milestone.
Built end-to-end (R-VERTICAL): **api_scopes** (read:audits/read:findings — no
write scope by design), **api_auth** (one bearer resolver for rt_ personal
tokens AND at_ OAuth tokens → ReadPrincipal; tenancy at the web boundary, the
engine stays tenant-blind; scope miss = 403), **routes_api_read** (GET
/api/v1/audits + /audits/{id}/findings — counts/dollars only FR-22, scoped to
the caller, other-tenant = 404 not 403 so no existence oracle),
**routes_oauth** (authorization-code + PKCE S256: consent bound to the logged-in
owner via a signed short-TTL blob = CSRF-safe; redirect_uri matched BYTE-EXACT,
unknown client/redirect shown on-site never redirected = open-redirect guard;
/oauth/token requires client_secret AND PKCE, single-use codes under a row lock,
RFC-6749 error format), **routes_developer** (Developer Settings — mint/revoke
tokens, register/revoke apps, Pro+ gated, shown-once reveals, hash-only at rest,
app-revoke kills every token it issued). Four new models + migration 019 (chains
018); five templates; sidebar Developer nav (reachability). ERROR_CODES gained
403 forbidden. Read+OAuth sections added to the API reference, accuracy-pinned.
Ingest key stays WRITE-ONLY (separate credential class — never scoped for read).
Tests: tests/test_developer_platform.py 24 green (both journeys + the adversarial
OAuth cases). ruff+mypy clean. Deferred to BACKLOG (one line, R-IMPROVISE): the
logged-out authorize deep-link return (interstitial is honest meanwhile).
Gate round next: cold (auth/scoping/OAuth), spec (FR-22/X-scope/traceability),
system-tester (journey), ux (Developer surface). Then O-0.

## API reference docs — GATE ROUND CLOSED (2026-07-24) — spec PWN · cold PWN, both notes applied

Both gates PASS-WITH-NOTES; every note applied (doc edits + new pins), full
chain green (17/17 docs tests, whole suite exit 0). cold-reviewer's three
accuracy fixes, each verified against the real handler before editing:
(f.1) SDK `init(environment, tag)` folds both into ONE 120-char `tag` and
`tag` wins — the doc no longer implies both are captured; (f.2) status body
keys `valid_pct`/`queue_position`/`error` are each CONDITIONAL in
routes_upload.py — the example now shows a `queued` body and the prose says
"code to the presence of each key," so an integrator can't KeyError on an
early poll; (f.3) the `[0, 1_000_000_000_000]` integer ceiling
(`_MAX_COUNT`) was undocumented — now in the field table and the broadened
422 row. spec-guard's coverage note closed by test_06: it walks the app's
lazily-wrapped route table (`_IncludedRouter.original_router`) and pins all
six documented routes as really registered; test_07-09 pin each cold fix to
code (`_MAX_COUNT` imported directly). Next: the SDK queue (S-6, O-0).

## API reference docs (2026-07-24) — Anthropic-style, multi-language, tied to the code

Founder: "proper API documentation very similar to claude documentations,
all the apis with examples in different languages." Built a CURATED
reference (docs-site/api/reference.md) alongside the existing
auto-generated endpoints.md (which stays — CI regenerates it, MP-3).
Covers, developer-facing and accurate to the real routes: ingest-key/DSN
auth (Bearer ik_, write-only trust boundary), POST /api/v1/ingest with the
full counts-only record schema + MULTI-LANGUAGE examples in pymdownx tabs
(curl · Python requests · Python SDK · TypeScript · Go), audit status,
signed report retrieval (/r/{token}[/pdf]), the Python SDK (the three
guarantees), idempotency, per-key+per-IP rate limits, the NFR-14 error
envelope with a code table matching ERROR_CODES exactly, and webhooks.
mkdocs builds clean (exit 0, tabs render). Accuracy is TEST-PINNED
(TestApiReferenceAccuracy): the doc's error codes are tied to the app's
ERROR_CODES map, the ingest path/auth/env-var are asserted, the language
tabs are required — so the reference can't drift from reality silently.
Full chain green. Gate: spec (accuracy/no-overclaim) + cold (every
documented contract matches the code). Then the SDK queue (S-6, O-0).

## WP-COPILOT-AGG CLOSED (2026-07-24) — re-gate PASS; "proceed on connectors" COMPLETE

system-tester re-gate PASS-WITH-NOTES: live render confirms the seat report
carries none of the misleading token copy, the honest replacements are
present, FR-22 holds, and the TOKEN report path did not regress (else-
branches byte-identical, test_report_web still green). Its symmetric-
coverage note actioned: test_trep08b pins that a token report KEEPS
"scaled to 30 days" + "machine-verified" and shows no seat-copy bleed — so
a future seat-branch edit can't silently regress the token path either
direction. WP-COPILOT-AGG closed.

"proceed on connectors" is now COMPLETE: five model-cloud connectors
(OpenAI/Anthropic/Azure/Bedrock/Vertex, agent-verified pricing), the
SDK+API (S-0/S-1), Copilot seat governance (the first non-token analysis,
honest per-seat-rate framing), and the visible Works-with coverage map.
NEXT per "and then sdk queue": S-6 (read API tokens + OAuth apps +
developer settings), then O-0 (the workspace tenancy spine, R-ORG).

## WP-COPILOT-AGG gate round (2026-07-24) — spec PWN · cold PWN · system-tester FAIL→fixed

The report-template mismatch I flagged was real and both cold + system-
tester caught it. system-tester FAIL: the seat report rendered "machine-
verified date unavailable" (asserting a verification that never ran).
cold PWN corroborated: f.1 equiv banner "API-equivalent token value"
wrong for seats, f.2 "N-day window scaled to 30 days" false (seat report
is a snapshot, observed_days=1, no scaling), f.3 the provenance line, f.4
CSV pending "0" truthy. ALL FIXED: _report_body.html now branches on
tier=="seat-governance" for the header (seats reviewed, not calls), the
equiv banner (stated-rate wording), the "current monthly spend" caption
(seats × rate, no scaling claim), and the provenance section (the rate is
a stated input, NOT machine-verified — SaaS seat prices outside the token
feed by design). report.py passes a SEAT_METHODOLOGY (the token
methodology mentioned the verified rate card + 30-day scaling — none
apply). f.4: "0" added to the pending exclusion set. Landing "on the way"
→ "ships now" (system-tester f.6). Journey test now ASSERTS the seat
report carries no "machine-verified"/scaled-window/token-methodology copy
and shows the honest input-rate line — the class can't regress. spec PASS-
WITH-NOTES (R-COPILOT recorded, X-02/FR-22/NFR-01 clean; its note was the
same headline-field concern, resolved by the tier-aware framing). Full
chain green. Re-gate system-tester on the fix diff, then COPILOT closes →
SDK queue (S-6, O-0).

## WP-COPILOT-AGG (2026-07-24) — Copilot seat governance; the tool-layer answer, built

R-COPILOT ruled A/P1; built end to end (R-VERTICAL). The FIRST non-token
analysis on the platform: Copilot bills per SEAT, so the waste is IDLE
SEATS. services/copilot/seats parses the admin seats export (the
/copilot/billing/seats JSON or a CSV) reading DATES ONLY — the SeatRecord
type has no login field, so a username in the export CANNOT survive into a
record (FR-22 by the type itself; test feeds "SECRET-USERNAME" and proves
it's gone). analyze() → idle/never-used/pending counts; build_finding() →
d7_idle_seats, LABELED seat governance (not a token detector), monthly $ =
idle × the STATED rate (default GitHub Business list, customer-confirmable
— R-COPILOT P1, sits outside R-AUTO-PRICING by construction since SaaS seat
prices aren't in the per-token feed; the finding's confidence=ESTIMATED and
detail.rate_is_input=True say so). services/copilot/report assembles the
seat finding into the EXISTING report shell (Option A), tier=
"seat-governance", equiv_spend=True (the honest "billing depends on your
plan" framing, same as Claude Code). Route POST /copilot/seats → signed
report; reachable via a REAL upload form in the get-logs Copilot tab (knobs
bounded; UTF-8/size guarded). X-02 intact: we surface idle seats, the
customer reclaims. Fixed in-slice: get-logs tab count pin 5→6, no inline
price literal (config-only law). 8 tests, full chain green. Gate round
next. This completes "proceed on connectors": 5 model clouds + SDK/API +
seat governance + the honest Works-with map. Then the SDK queue (S-6, O-0).

## Works-with rider CLOSED (2026-07-24) — ux PWN fixed, spec + system-tester PASS

ux PASS-WITH-NOTES → both fixed: the .connect-cards-4 grid variant (ux's own
suggestion — 4-up desktop → 2 at 1100px → 1 at 620px, clean quad not a 3+1
wrap) and the tighter h2. spec PASS (no overclaim; seat tools future/
attribution/no-data framing verified against BACKLOG). system-tester PASS
zero findings (all five landing-named providers actually reachable at
/sources/connect/*; 300KB budget ~39% headroom; no dead links; no stale
"two providers" copy anywhere). "proceed on connectors" has now delivered:
C-C Vertex (5-provider model-cloud set COMPLETE) + the coverage made
visible on the landing. Remaining connector: WP-COPILOT-AGG (seat
governance — a DIFFERENT analysis kind). Then SDK queue (S-6, O-0).

## "Works with" landing rider (2026-07-24) — the coverage is now visible + two honesty gaps closed

Founder connectors question → after completing the 5-provider model-cloud
set, made the coverage VISIBLE on the landing (R-SDK-PLATFORM §5 rider).
Reuses the connect-card grammar (no new CSS, 300KB budget honored): a
four-tier map — model providers (all five named), your own code (SDK/API),
upload (anything), and seat tools stated HONESTLY (Copilot governance
coming; Cursor/Lovable already counted via provider keys; Figma AI has no
token data to audit — said, not pretended). IMPROVISED honesty fixes
(R-IMPROVISE): the hero-sub "No SDK" claim and the og:description "No SDK"
were both FALSE after S-1 shipped an SDK — reworded to "No proxy, nothing
in your request path" (the observe-only SDK is still never in the path, so
the claim stays true); connect-tools now names the five providers. Tests:
five providers named, SDK+API+upload paths present, seat-tools honest +
"No SDK" gone. Full chain green. Gate: ux (landing is its charter) + spec
+ system-tester. Then WP-COPILOT-AGG, then the SDK queue (S-6, O-0).

## C-C re-gate note (2026-07-24) — bounded the pagination loop I introduced

cold re-gate PASS-WITH-NOTES confirmed the three fixes closed, but flagged
that my nextPageToken loop had no cap/repeat-guard — a server echoing the
same token forever would hang the pull and pile buckets. Fixed: the loop
now breaks on a repeated token (before re-fetching, so no double-count) and
_MAX_PAGES=1000 is the hard backstop. test_04d proves a stuck-token server
terminates at 2 fetches with prompt_tokens=20, not an unbounded pile.
C-C CLOSED. Full chain green.

## WP-CLOUD-T2 C-C gate round (2026-07-24) — spec PASS · vv PASS · system-tester PARTIAL-clean · cold PWN fixed

spec PASS 7/7 (incl. R-AUTO-PRICING: vertex rows agent-verified 35/35, no
FOUNDER-VERIFY flag). vv PASS (suite green, coverage 95.2%, vertex_usage
91.6%, all four goldens hand-recomputed). system-tester PARTIAL by budget
but every surface reached PASSED (five providers, textarea, no wizard
regressions, no dead links); its incomplete items crashed on ITS OWN
harness bug (imported a nonexistent RuleResult), not a product defect —
run_pull upserted=3 as expected. cold PASS-WITH-NOTES, all three fixed:
f.1 _fetch now follows nextPageToken and MERGES paged (day,model) buckets
(the Bedrock chunk-truncation lesson — a busy project's series can't be
silently dropped while pages=1 lies); f.2 docstring corrected (the key
lives for the pull's duration, not "one signing pass"); f.3 int64Value
parsed as int directly (Google sends it as a string to avoid float
rounding — test proves 9007199254740993 survives exact). Adopted
system-tester's suggestion: test_06b proves a fresh Vertex source PRICES
gemini-2.5-pro end to end with nonzero spend (money-math honesty, not just
unit coverage). Full chain green. Re-gate cold on the fix diff, then C-C
closes → WP-COPILOT-AGG, Works-with rider, SDK queue.

## WP-CLOUD-T2 C-C (2026-07-24) — Google Vertex AI connector; the model-cloud set is complete

Built end to end (R-VERTICAL) on the founder's "proceed on connectors".
connectors/vertex_usage reads Vertex's Cloud Monitoring token_count metric
(aiplatform.googleapis.com/publisher/online_serving/token_count, input/
output by model_user_id — VERIFIED against Google docs + integration refs)
via the SA-JSON service-account flow: an RS256 JWT (stdlib base64/json +
cryptography for the signature — cryptography already a dep via Fernet, NO
new dep) exchanged at token_uri for an access token, then Cloud Monitoring
v3 timeSeries.list with roles/monitoring.viewer. Credential = the whole SA
key JSON on the Fernet path; wizard uses a registry-driven TEXTAREA field
(the template gained textarea support). CACHE-BLIND like Azure (this metric
has no cache split) → cached_tokens=0, d2 not run, coverage "not observable
on Vertex" (the blind note is now provider-named). MONEY: Gemini rows
mirror the feed (2.5-pro 1.25/10, 2.5-flash 0.30/2.50, 2.5-flash-lite +
2.0-flash 0.10/0.40); goldens G24-G27 independent-Decimal; count pin 23→27;
the STRICT gate scripts/pricing_verify.py corroborated all four against the
feed — 35/35, NO human gate (R-AUTO-PRICING working exactly as ruled).
Non-Gemini/older Vertex models unpriced (FR-28). Now FIVE model providers:
OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, Google Vertex AI. Guard pins
extended (console.cloud.google.com domain + "service account" wall phrase).
11 tests, full chain green. Gate round next; then WP-COPILOT-AGG (seat
tools), Works-with rider, then the SDK queue (S-6, O-0).

## S-1 CLOSED (2026-07-23) — cold re-gate PASS, all four fixes verified

cold re-gate PASS: f.1 DSN-parse-never-raises (bad-port env → inert, not a
host-app crash), f.2 IPv6 brackets, f.3 reinit closes the prior batcher
(no leak, no double-ship), f.4 functools.wraps — all confirmed against the
pinned toolchain, 18 tests exit 0. One minor non-blocking note (atexit
callback retention on pathological re-init) → BACKLOG line. Final S-1
verdicts: spec PWN · vv PWN · cold FAIL→fixed→PASS. The Python SDK is
done: one call, counts-only by construction, observe-only, shipping to
the S-0 endpoint. Queue advances to S-6 (read API platform), then O-0
(workspace tenancy spine) on the founder's word.

## S-1 gate round (2026-07-23) — spec PWN · vv PWN · cold FAIL→fixed (re-gate pending)

spec PASS-WITH-NOTES (all 6 checks; its note: the PEP-758 bare-except is
ruff-format-enforced on 3.14 — kept per TE-11 pinned-toolchain authority).
vv PASS-WITH-NOTES (suite green EXITCODE=0, coverage 95.0%, money paths
100%, every SDK guarantee independently verified; note: add formal
T-SDK-xx ids in a follow-up — prose descriptions in docs/04 for now,
consistent with S-0). cold FAIL, all four fixed: f.1 _parse_dsn's .port
access now INSIDE the try (a typo'd DSN env var returned None, never
crashes the customer's init — this was the severe one: an SDK that breaks
the host app); f.2 IPv6 hosts keep their brackets; f.3 a second init()
CLOSES the previous batcher (was leaking the thread AND double-shipping
every call); f.4 functools.wraps on the wrapper (introspection intact).
Four proof-tests added (bad-port/IPv6 never-raise, reinit-closes-first,
bad-DSN-env inert, wrapper-preserves-name). Full chain green. Cold
confirmed the load-bearing guarantees hold: X-01 wrapper propagates the
customer's OWN exceptions (real call outside the try), FR-22 clean, inert
path leaks nothing. Judgment: ux/system-tester not run for this
client-library slice (only surface change is a snippet in the already-
gated S-0 reveal). Re-gate cold on the fix diff, then S-1 closes.

## S-1 (2026-07-23) — the Python SDK: one call, usage flows, counts-only BY CONSTRUCTION

Built end to end (R-VERTICAL). `import tokenops_cost_auditor.sdk as toca;
toca.init()` reads TOKENOPS_COST_AUDITOR_DSN and auto-instruments the
OpenAI + Anthropic client libs. THREE load-bearing guarantees, each
test-pinned: (1) FR-22 BY CONSTRUCTION — sdk/extract reads only
usage/model/timing off the response, never choices/content; a record
built from a response whose text fields are POPULATED contains no text
(test asserts "SECRET" not in str(record)); only allowlisted contract
fields emitted. (2) X-01 OBSERVE-ONLY — the instrument wrapper runs the
REAL provider call first and returns it UNMODIFIED; recording is
best-effort in a try/except so a broken recorder (or our whole SDK)
never breaks, slows, or alters the customer's call (test: a raising
recorder still returns the real result); the batcher's record() never
blocks (bounded deque, drops-counted under backpressure) and never
raises; ship failures are swallowed — no retry-storm. (3) anthropic cache
composition mirrors anthropic_usage (input + cache_read + cache_creation).
Transport is stdlib urllib (zero new dep, SDK-only users pull nothing
heavy), FR-26 idempotency key per batch, atexit flush for short scripts.
Reveal now shows the Python snippet + the any-language curl; quickstart
gains an SDK section. e2e test: SDK-built records → /api/v1/ingest → done
audit, no export step. 14 tests, full chain green. Gate round next; then
S-6, then O-0.

## S-0 gate round (2026-07-23) — spec PASS · vv PARTIAL-clean · system-tester PASS · cold FAIL→fixed→PASS-WITH-NOTES→hardened

spec PASS 7/7. system-tester PASS zero product findings (full journey +
17-link crawl). vv PARTIAL by honest K-1 (all static checks clean; suite
already green in the pre-commit run). cold FAIL round 1 (5 findings) all
fixed a7cb282: empty-required rejected at the door, int/num ceiling, mint
cap row-locked (with_for_update — prod is Postgres; SQLite no-op is tests
only, same accepted precedent as saved-views/link-codes), DSN scheme
prepend, per-key rate bucket. Re-gate PASS-WITH-NOTES caught a REGRESSION
MY OWN f.5 fix introduced — bucketing on token hash let an attacker mint
a fresh 60/min bucket per guessed token, unbounding abuse. Fixed: a
stacked per-IP ceiling (_INGEST_IP_LIMIT 300/min) is the real bound;
per-key bucket stays for fairness. Both proof-tests the re-gate asked for
added (test_10 scheme-less DSN still embeds the token; test_11 rate-key
buckets per-token and falls to IP for non-ik/absent auth). Full chain
green. Lesson: a rate-key keyed on attacker-controlled bytes is not a
bound — pair per-principal fairness with a per-source ceiling.

## R-SDK-PLATFORM + S-0 (2026-07-23) — the Sentry adoption model ruled; the ingest DSN shipped

Founder ruling R-SDK-PLATFORM ("we need like Sentry platform where people
can configure and use our platform") recorded in PRD Amendments;
PLAN-SDK.md RULED — build order S-0 → S-1 → C-C. S-0 built end to end
(R-VERTICAL): IngestKey model + migration 018 (rehearsed); mint on
Sources (Pro+, shown once in the key-truth frame with the FULL DSN
TOKENOPS_COST_AUDITOR_DSN=https://ik_…@host, stored hashed, 10-key cap
stated); revoke DELETES the hash (authority law); POST /api/v1/ingest —
the documented generic-CSV contract IS the wire format so records drive
the existing T1 pipeline with ZERO new parser code (full six-detector
coverage); FR-22 AT THE DOOR as a strict allowlist: unknown fields
rejected 422 NAMING the offender, strings bounded (text can't smuggle
through tag), refusal-not-silent-drop by design; FR-26 idempotency;
60/min limit; plan-gated both halves (mint 403→/billing, lapse 402
"pauses"). Attribution end to end: paid_via="sdk", audit.source_id=key
→ /runs shows "SDK ingest", /explore lists "label (SDK)" (revoked stay
listed). ux mockup gate PASS-WITH-NOTES, all four notes honored in the
wiring (key-truth not an invented .panel; full uncut credential — the
shown-once law; uniform data-confirm revoke; one delight). Tests: 9,
including the DoD journey and envelope-aware (NFR-14) refusal pins.
Gate round next; then S-1 (Python SDK) on the standing order.

## WP-DEVOPS-OBS gate round (2026-07-23) — ops PASS · spec PWN · cold FAIL→fixed→PASS · system-tester PARTIAL→closed

ops-engineer PASS 11/11 (pipeline blocks on gate, concurrency, rollback
target matches provision's stamp with first-run guard, secrets names
match runbook, upsert idempotent, both Docker layers consistent with the
lock, zero-egress path, §2/§10 no contradiction). spec PWN — its real
catch merged into cold f.1; notes recorded: Dockerfile bundles the sdk in
every build (footprint only, zero egress without DSN — accepted), and
the traceability row lagged one commit inside the WP (process note:
same-commit next time). cold FAIL, all four closed in 1d5dc52 and
RE-GATED PASS: f.1 include_local_variables=False + _scrub strips frame
vars/extra/contexts (defense in depth; test proves ABSENCE of the
sensitive value, stack survives); f.2 _sentry_enabled reset
unconditionally before the DSN check; f.3 blind spots tested; f.4
first-run rollback skip called out in runbook §10 + prod hand-stamped
RELEASE_TAG=v1.7.0 so the first pipeline run has a real target.
system-tester PARTIAL (honest K-1): its Q1 (dual-DSN boot walk) closed
EMPIRICALLY by test_05 — which itself caught the armed test leaving the
global SDK live (egress attempt at session exit); teardown disarms. Its
Q2 answered: no pricing files in this diff — the strict verify runs in
CI and the deploy gate regardless. Full chain green; main kept current.
AWAITING FOUNDER ACTIVATION (runbook §10 checklist): repo create+push
(agent permission-blocked), secrets, branch protection, SENTRY_DSN,
UptimeRobot. Queue resumes at C-C Gemini/Vertex on "proceed next".

## WP-DEVOPS-OBS (2026-07-23) — error tracking, PR/CI-CD, the lifecycle codified; v1.7.0 DEPLOYED first

Founder question ("why not sentry / proper PR + CI/CD / bug lifecycle /
observability?") → assessment → "proceed". v1.7.0 (both cloud connectors
+ R-AUTO-PRICING) DEPLOYED the proven way first: backup, runbook-4b
strict verify LIVE (31/31 — and its first ride caught its own same-day
restamp bug, fixed b867fde), provision, external smoke PASS (healthz,
both wizards auth-gated, head unchanged). Then the package: (A) Sentry
ACTIVATED in code — sdk as optional `obs` extra (customer in-VPC stays
zero-egress by not setting a DSN), FR-22 before_send scrubber (request
payloads/headers/cookies/query/env, breadcrumbs, user — stripped; stack +
route + release survive), release = deployed tag via provision.sh
RELEASE_TAG upsert (the only .env line it ever touches), tests. (B) main
fast-forwarded to the branch (177 commits); PR template carrying REV-X +
the standing laws. DISCOVERY: the repo had NO git remote — ci.yml has
never run on GitHub; repo creation was PERMISSION-BLOCKED for the agent
(publishing a repo needs the founder's own hand) — commands in the
runbook §10 activation checklist. (C) deploy.yml: workflow_dispatch(tag)
IS the approval ritual; gate job re-runs the chain + strict verify on the
exact tag; deploy job does backup → provision → external smoke →
AUTO-ROLLBACK to the prior RELEASE_TAG on failed smoke; §2 manual path
kept as fallback. (D) runbook §10: the detect→triage→fix→gate→deploy→
verify loop with named owners per step; log rotation audited (5x50MB
json-file per container — adequate); activation checklist (founder-lane:
create+push repo, secrets, branch protection, Sentry DSN, UptimeRobot).

## R-AUTO-PRICING gate round (2026-07-23) — spec FAIL→fixed→PASS · cold PWN all fixed · vv PARTIAL closed · system-tester PWN

spec-guard FAIL round 1: docs-site/concepts/pricing-data.md still carried
"## Human-verified, on the record" (capital-H escaped a case-sensitive
sweep — lesson: sweeps are case-INSENSITIVE from now on). Fixed 9041c51;
re-gate PASS-WITH-NOTES (rewording matches what verify+sync actually do;
its residue note → launch collateral + mockups swept in the fix commit;
PLAN/DOCS-PLAN history exempt). cold PASS-WITH-NOTES, all four fixed:
f.1 future-dated rows now status "not-applicable", EXCLUDED from the
verified tally (test_08); f.2 a feed-published write rate is compared
UNCONDITIONALLY — published data disagreeing with our structural default
now FAILS the gate (test_07 rewritten both directions; live feed checked:
only the 5.6 family publishes write rates and all match); f.3 feed
unreachable → clear message, exit 2 (distinct from mismatch=1; both block
— nothing ships unverified is the intent, recorded); f.4 dated snapshots
bucketed before -v keys (test_09). vv PARTIAL (honest K-1): its checks
all passed (strict exits proven live both directions, goldens untouched);
its leftover coverage run superseded by the main thread's full green
suite post-fixes. Its note on test_runner's self-referential date pin:
accepted — the report-template pin in test_report_web still anchors the
rendered string. system-tester PWN zero product findings (report shows
machine-verified 2026-07-23; popovers/wizard/guide correct; 60-link crawl
clean; 31/31 live re-confirmed; its three-phrasings note logged as copy
polish, not a bug). Verifier re-run after all fixes: 31/31.

## R-AUTO-PRICING (2026-07-23) — the human pricing gate is ABOLISHED; the agent verifies strictly

Founder ruling (verbatim in substance): "all prices have to be automated
and no human gate — it has to be done by the agent strictly verifying."
Amends the founder's own R-Q3 hand-verification step; recorded in
CLAUDE.md rule 4, docs/00-PRD Amendments, and auto-memory. Built the same
hour: scripts/pricing_verify.py — a STRICT release gate (no advisory
mode): every (provider, model) row effective TODAY in the merged table
must be corroborated EXACTLY per-1M by an independent machine-readable
source or the run exits 1. Source ladder recorded honestly: the OFFICIAL
price APIs were probed live and LAG the current model generation (Azure
Retail Prices: zero gpt-5.x meters across 7,573 Azure OpenAI + 1,431
Foundry eastus meters; AWS Bedrock price list published 2026-07-23 still
carries only Claude 3) — so the corroborating source of record is the
LiteLLM feed (independent of this repo; already the R-LIVE-PRICING sync
source), with dated/versioned key fallbacks (azure/<model>;
anthropic.<model>-YYYYMMDD-vN:M). cache_write compared only when BOTH
sides publish it — a structural default is not a provider number. FIRST
RUN: 31/31 rows verified, including azure G16-G19 and bedrock G20-G23 —
the two sections previously awaiting founder eyes are now agent-verified
and v1.7.0 is unblocked. Wiring: CI step (fails the build), runbook §2
step 4b (pre-deploy, --stamp), last_verified semantics = last successful
agent verification (NFR-15 freshness now measures the machine). Copy
sweep: every "human-verified" claim (report docstring + _report_body,
help_registry ×4, docs-site ×3, PRD) reworded to "machine-verified
against independent published price data" — the product may not claim a
human it no longer has. Two brittle date pins made dynamic
(test_report_web trep08, test_runner TREP08). 7 verifier tests, full
chain green.

## WP-CLOUD-T2 C-B (2026-07-23) — AWS Bedrock connector built + gated; DEPLOY BLOCKED with C-A on founder golden verification

Slice C-B end to end (R-VERTICAL). connectors/bedrock_usage.py reads the
AWS/Bedrock CloudWatch namespace (Invocations / InputTokenCount /
OutputTokenCount / CacheReadInputTokens / CacheWriteInputTokens by
ModelId; VERIFIED against AWS docs 2026-07-23) via stdlib-SigV4-signed
JSON-protocol POSTs (no AWS SDK). Credential = 3 fields (access key id,
secret, region) packed to canonical JSON on the Fernet + fingerprint
path; is_valid_region() public for the route pre-check. Token composition
mirrors anthropic_usage VERBATIM (prompt = input + cache_read +
cache_write; cached = cache_read). Bedrock EXPOSES cache counts → d2 RUNS
here (test-pinned mirror of Azure's blindness). ModelId normalization
strips region-routing prefixes + -vN:M suffixes ("us.anthropic.claude-
sonnet-5-v1:0" prices as "anthropic.claude-sonnet-5"). Wizard fields now
REGISTRY-DRIVEN (copy.fields; azure migrated — no template forks) and
every provider's honesty_note renders in the MAIN column before the CTA
(fixed the mobile stacking gap in both cloud wizards, ux C-B note 4).
MONEY: bedrock rows mirror anthropic exactly (on-demand parity, sonnet-5
epochs); goldens G20-G23 independent-Decimal, pin 19→23; batch/PTU NOT
modeled (stated); Nova/Llama/Mistral unpriced-never-guessed (FR-28),
disclosed pre-connect. Guard pins extended CONSCIOUSLY: OFFICIAL domain
set + per-provider wall-phrase map (a new provider without a registered
wall phrase now fails the suite). Gate round (commit 7800d50): ux mockup
PWN ("grammar exemplary") · spec PASS (8/8) · vv PASS (all four goldens
hand-recomputed ✓, bedrock_usage 91.8%) · cold PWN → f.1 docstring
lifetime honesty, f.2 is_valid_region() public, f.3 chunk/NextToken
accumulation pinned (101 models, 4 pages, counts land exactly once) ·
system-tester PWN zero product findings (real in-process pull→audit
priced $0.18; 16-target crawl clean; N1 note: the validate hx target
fires a real signed AWS call — mind networked CI crawlers). Fixes commit
ed14f67; full chain green. NEXT: founder verifies BOTH pricing sections
(azure-openai G16-G19 + bedrock G20-G23) → deploy v1.7.0 together.
Queue after: C-C Gemini/Vertex.

## WP-CLOUD-T2 C-A (2026-07-23) — Azure OpenAI connector built + gated; DEPLOY BLOCKED on founder golden verification

Queue card WP-CLOUD-T2, slice C-A, end to end (R-VERTICAL). Adapter
connectors/azure_usage.py reads Azure Monitor platform metrics on the
Cognitive Services resource (ProcessedPromptTokens / GeneratedTokens /
AzureOpenAIRequests, Sum, split by ModelName; api-version 2023-10-01;
VERIFIED against Microsoft's monitoring reference 2026-07-23 — Azure has
no OpenAI-style usage endpoint). Auth = Entra ID client-credentials; the
credential is FOUR fields packed to canonical sorted JSON (fingerprint
dedup works), encrypted whole on the existing Fernet path. Honesty bound:
Azure exposes NO cached-token count for standard deployments →
cached_tokens=0 by construction, d2 NEVER runs on azure-openai
(CACHE_BLIND_PROVIDERS), coverage says "not observable on Azure", wizard
step-3 discloses it BEFORE connect. Wizard: cred-grid (promoted to
wa-design.css both copies), five portal steps, Monitoring-Reader RBAC
trust copy ("Azure enforces it, not our promise"), Azure-worded refusal
verdicts (secret vs role-gap). R-CONNECT-VISIBLE: sources buttons,
get-logs tab, wizard switch links, account-paths guide all list Azure
from day one (routes_pages._render now injects help for the tabs).
MONEY: prices.yaml azure-openai Global-Standard rows mirror the openai
list (gpt-5.5/5.4/5.4-mini/5.4-nano/5.3-codex; 5.6 family deliberately
NOT mirrored — FR-28 unpriced, never guessed); goldens G16-G19
independent-Decimal, count pin 15→19; NOTES derivation + FOUNDER-VERIFY
flag. Gate round (commit bc1b6ae): ux mockup PASS-WITH-NOTES (notes
honored) · spec PWN (its note: the verify flag is textual — the
structural block is that deploys happen only on founder approval) · vv
PWN (goldens hand-recomputed, all match; azure_usage 92.3%) · cold PWN →
f.1 round-not-truncate on float Sums, f.2 status-0 → bad-credential
verdict, f.3 registry annotation widened · system-tester PWN → R-WIZ-
DEGRADE now proven end to end with the HTTP client itself failing
(test_13; saves + says "saved"). Fixes commit 14a7de1; full chain green.
NEXT: founder verifies azure pricing rows against the Azure pricing page
("azure goldens verified" or corrections) → deploy v1.7.0. Queue after:
C-B Bedrock.

## WP-PIPELINE-UI (2026-07-23) — runs observatory shipped; FR-31 closed; five gates run

The queue's card 2, end to end as one slice (R-VERTICAL). /runs (nav:
Monitor) lists EVERY audit — trigger (paid_via mapped to scheduled pull /
collector ship / file upload), status, duration from recorded StageEvents,
kit-ribbon drawers (rich form + new cls hook, ribbon-4 track variant; ONE
grammar, F4 honored), per-detector drill with honest zeros verbatim, FR-31
purged rows metadata-only, pre-017 runs honestly say they predate stage
timing, in-flight rows self-poll and link to the theater; idle pages never
poll. Migration 017 (stage_events, pull_events with `updated` col renamed
from a misnamed `skipped`, alert_checks), rehearsed to head. Instrumented:
runner._pipeline + run_source_audit (4 StageEvents each, TRUE execution
order — bucket audits detect before pricing), run_pull success row rides
its own transaction, record_pull_failure (fixed user-safe strings only;
schedule tick + first-pull worker, pull_ok flag so audit-step failures are
never mislabeled), run_for_user AlertCheck per enabled rule committed
before mail. F14 nav-group CSS dedup folded in (both pinned copies).
Gate round: ux mockup v1 FAIL → v2 PASS-WITH-NOTES (note applied:
processing badge → neutral). spec-guard PASS. vv-engineer PASS (suite by
exit code; coverage: dispatch 100%, pull 97.9%, source_audit 98.9%,
runner 93.6%, TOTAL 95.4%). cold PASS-WITH-NOTES → f.1 stale-StageEvent
delete on re-driven pre-created rows + rerun test; f.3 commit contract
documented; f.4 per-row priced_rows honesty; f.5 swallowed ledger failure
now logged; f.2 DECLINED with reason (UI renders stored stages verbatim —
dedup lives at the source, masking storage bugs in the template is
dishonest). system-tester PASS-WITH-NOTES → REAL catch: per-detector
cent-rounding could sum to $2.20 vs dashboard's $2.19; fixed with an
"Identified" drawer total summed BEFORE rounding + scope words, pinned by
cross-surface test_14; its admin-route question answered: admin mounts
only when ADMIN_TOKEN is set (test env has none) — not a gap. Commits
aa37e18 + 8e1f243. Pending: founder "approved to deploy" → v1.6.9
(backup, alembic to 017, CHANGELOG).

### C3 gate round (2026-07-23) — spec PASS · cold PWN fixed · vv PWN closed · system-tester PARTIAL→FAIL→PASS

spec-guard PASS 8/8 (scope = rulings exactly; export absent; R-F1 strings
untouched; TE-5 amendment consistent). cold-reviewer PASS-WITH-NOTES, all
fixed 8bdb2bd: f.1/f.2 save_view row-lock (the G-V1 count-then-insert race
class — cap race + same-name 500 closed), f.3 migration 014 created_at →
NOT NULL (edited in place; never deployed; chain re-rehearsed).
vv-engineer PASS-WITH-NOTES (K-1 honest stop): both open items closed by
main thread — full suite + coverage gate green (services 96.7%, money
math 100%); f.5 field-ledger round-trip test added (a Filters field
without a serialize branch now fails a test, never silently drops).
system-tester: PARTIAL (K-1) → live-walk FAIL with the round's best
catch — dashboard "$15/mo identified" vs explorer "$45/mo", two TRUE
facts at different scopes wearing one word — fixed 1052957 by stating
scope in words on both surfaces ("identified — latest audit" / "across N
findings in this slice") + two-audit journey pin → final re-gate PASS
(8/8 re-derivation, single-audit case still agrees at $100=$100).
Role ledger to date: 6 sweeps, 8 findings, 7 real fixes test-pinned,
1 lawful R-Q9 decline, 0 found by the founder.

### M-FLY-0 gate round (2026-07-23) — three gates, no FAIL, all notes actioned

vv PASS-WITH-NOTES → f.3 config-mutation guard added (same data, custom
thresholds flip rungs — a hard-coded 10 now dies in test), f.4 L2 24/25
boundary pinned, f.6 both founder surfaces rendered for real (digest via
build_digest, admin fetched through its token gate). spec-guard
PASS-WITH-NOTES → f.1 accepted-as-designed: frame enforcement is
schema/type-level; runtime enum values are enforced upstream at
FindingRow constraints (recorded); f.8 traceability citation made
precise. cold-reviewer PASS-WITH-NOTES → f.1 FIXED: cross-RUN determinism
(input findings sorted on a total key incl. finding_id/id before mapping;
stable export sort preserves it — same-audit twins no longer ride DB scan
order), f.2 FIXED: a flywheel exception can never 500 the admin panel
("Flywheel: unavailable" fallback), f.3 FIXED: L3 note reads "needs 6mo
history", f.4 FIXED: unknown row_count/observed_days pass through as
None, never fake zeros (schema types widened; allowlist unchanged).

### WP-CC-LINK gate round (2026-07-23) — spec PASS · cold PWN fixed · system-tester PARTIAL→answered

spec-guard PASS 7/7 (consent law both halves, no bypass anywhere, FR-22
columns clean, exporter lift byte-for-byte, R-VERTICAL journey complete,
residue registered). cold-reviewer PASS-WITH-NOTES, all four fixed: f.1
one-shot code claim now UPDATE-where-unconsumed rowcount-checked (the
check-then-set race class, third catch today — source-pinned); f.2 the
consent trust boundary stated HONESTLY (the TTY prompt lives in the CLI;
the server verifies the ASSERTION and audit-logs it — docstring no longer
overclaims); f.3 device config written 0600 from birth (no world-readable
window — pinned by an actual stat() test); f.4 link/ship rate-limited per
the codebase's own NFR-03/12 pattern. system-tester PARTIAL (K-1) → its
recon gap CONFIRMED REAL and fixed (R-IMPROVISE): the explorer's selector
now NAMES linked machines ("hostname (Claude Code)") so the eye-link
lands on a selector that says what it selected; its four open questions
all answered as standing journey tests (plan gating via the ADMIN GRANT
product path, consent words on the partial, device slice narrows,
findings render). One test-side false alarm honestly resolved: the
'Link a machine' PROSE renders for all plans (it describes the surface);
the CONTROL is what's gated, and that is what the test now asserts.

## WP-CC-LINK core (2026-07-23) — one command, one consent; the T3 journey is live end to end

Vertical per rule 9: dashboard mints a one-shot hashed code (10min, Pro+)
→ CLI `link` prints the consent text and REFUSES without a person typing
'I agree' at a TTY (no bypass flag exists — R-CC-LINK 2, both halves
tested: server rejects consent!=true, CLI refuses non-TTY and wrong
words, network provably untouched before consent) → device token minted,
HASHED at rest, consent_at NOT NULL by schema, audit-logged → `ship`
exports counts via the lifted transcripts core (scripts exporter now a
thin wrapper, contract unchanged) and lands a REAL audit through the T1
pipeline (FR-26 idempotent — cron re-ships replay; paid_via=collector;
device-grade source_id attribution) → Sources shows the machine with
last-ship + eye/unlink actions → revoke refuses the next ship in plain
words while history stays. Plan lapse pauses ships honestly (402 'ships
pause until it resumes'). Migration 016 rehearsed. RESIDUE (slice 2,
recorded in BACKLOG): PyPI short-name publish (founder-lane), skill
auto-install, self-update. Gate round next.

## R-REACHABILITY (2026-07-23) — why the validator missed it, and the laws that close it

Founder question after the unlinked-Anthropic escape: "why is this not
captured by the system validator?" Root cause recorded in docs/10
amendment 2026-07-23b — three blind spots, three laws: (1) the crawler
checked links pages EMIT, not what the product DECLARES → new CI law
TestDeclaredEqualsReachable (registry inventory ⊆ click-closure from
/dashboard); its FIRST run caught a second live instance the same day
(/guide/benchmarks reachable only via the dormant benchmark widget —
guide_index now lists synthesized pages); (2) milestone-scoped walks never
chose the connect journey → charter: every shipped surface reached by
CLICKING, never by URL; (3) walks ORM-granted plans, so nobody ever saw a
real Free account → charter: one flow per run as Free AND as a granted
plan, via the admin grant endpoint (runbook §9), never SQL. Plus the
plan-reality render test (free=1 / team=5 stated on /sources).

## M-FLY-1 (2026-07-23) — L1 peer benchmarks, both surfaces; gate round FAIL→fixed

Widget (mockup ux-gated first, all notes actioned) + report block; dormant
= ABSENT below n≥10; ranks the engine's OWN savings_pct (no new money
math); percentile golden FOUNDER-VERIFIED. GATE ROUND: spec-guard PWN
(all laws hold; deviation recorded: shipped live-compute vs the plan's
nightly precompute — correct at today's scale; precompute = a scale
trigger); vv PWN (golden recomputed independently — exact; caught the
traceability row committed late (rule 5 slip — row rides this gate-round
commit) + demanded the widget-side key allowlist, added test_21);
system-tester PWN (live walk exact incl. opt-out arithmetic 4-of-11→36th
through the real endpoint; demanded the standing cross-customer opt-out
journey — added); cold-reviewer FAIL, all four fixed: f.1 SELF-INCLUSION
POLICY unified — every path injects the in-flight audit's own
savings_pct (own_value, authoritative over stale rows), so upload and
connector paths can never disagree on a rank (test_20 + source pins);
f.2 cohort candidates sort (when,id) — DB return order can never pick a
winner; f.3 naive rows normalize to aware UTC at read (no suppressed
comparison); f.4 tie rule golden-pinned (ties share the higher rank;
all-equal cohorts rank everyone p=100 — stated, accepted; NOTES row).
Re-gate (cold) on the fixed diff follows; then v1.6.1 deploy per the
founder's standing approval this session.

## M-FLY-0 (2026-07-23) — the flywheel's data spine: training frame (A1) + cohort ledger (A2)

First flywheel milestone, built the day its blocker lifted. A1:
services/flywheel/frame.py — FRAME_COLUMNS is the executable schema
(ENUM_OR_ID law: a free-text column cannot ship, T-FLY-02 names the
offender), keyed one-way cohort_pseudonym (HKDF context distinct from
credential crypto), deterministic extract, benchmark_sharing=False
excluded from the FIRST BYTE (R-F1 column contract, T-FLY-04);
scripts/flywheel_extract.py ops CLI (JSONL to stdout, zero network). A2:
services/flywheel/cohort.py — rung ledger (L1 n≥10 audited / L2 n≥25
labeled / L3 n≥50 + 6mo, all thresholds config), exact-boundary tests
(9≠10), surfaces = founder ops digest line + admin row ONLY — customers
never see a countdown (zero-state law, template grep enforced,
T-FLY-08). Package posture pinned: flywheel imports no network/rules/
pricing/connectors (T-FLY-09, R-F4 — the guard never meets an ML lib; no
ML lib exists to meet). DECISIONS: L1 keys on audited customers, L2 on
labeled customers, L3 on audited + platform history span — recorded here
for the rung builds to inherit. NEXT (queue order): founder deploy, then
WP-CC-LINK → WP-PIPELINE-UI → WP-CLOUD-T2; M-FLY-1 (L1 benchmarks,
dormant-until-10) may interleave after its ux mockup gate.

## R-F1-SIGNOFF (2026-07-23) — the promise amended and shipped; Tracks A/B unblocked

Founder signed off the option-A sentences; applied verbatim the same day
on every surface that carried the old promise (footer/landing, legal
web+docs-site mirrors, report DATA_HANDLING — one constant feeds HTML and
JSON, so the report cannot drift). Benchmark toggle shipped: users.
benchmark_sharing (migration 015, chain 001→015 rehearsed), default ON
per R-PROCEED Q7 and STATED in words ("Included by default — uncheck to
opt out", ux f.5), one-checkbox opt-out, audit-logged both directions.
GATE ROUND — three gates, no FAIL, no bug: spec-guard PWN (notes
actioned: disclosure added to BOTH Terms surfaces per the amendment's
letter; UAT2-KIT + launch-assets drafts brought in line; stale STATUS
"still the blocker" line reconciled; settings paraphrase RECORDED as
accepted page-relative deviation from the ruled disclosure — the signed
sentences stand verbatim on privacy/terms); ux PWN (f.5 default stated,
f.6 "cohort"→"benchmark group"); system-tester PWN (live walk: promise
verbatim on all five surfaces, opt-out round trip + audit-log sequence
confirmed; its K-1 overrun disclosed with cause — discovery cost, no
open questions). v4 design mockups keep the old phrase as historical
artifacts (spec f.9, accepted). PLAN-FLYWHEEL Tracks A/B UNBLOCKED;
M-FLY-0 (A1 training frame + A2 cohort ledger) is next in queue order —
both MUST honor benchmark_sharing by the column contract.

## R-PROCEED (2026-07-23) — rulings recorded; C3 saved views + T4 spec shipped

Founder ruled "proceed" on the standing question lists; recorded as the
R-PROCEED PRD amendment (TAAS Q1-Q5 as proposed; FLYWHEEL Q4/Q5/Q6/Q7;
R-F1 OPTION A IN PRINCIPLE — exact promise sentences still need separate
founder sign-off before any copy/test change; TE-5 amended in docs/10 +
CLAUDE.md: Fable authors PRD/design, Opus implements, Sonnet gates).
BUILT THIS ROUND: (1) FR-32 C3 saved views — migration 014, whitelist-
sanitized params (parse→serialize round-trip: hostile keys cannot
persist), replace-on-same-name, 20-view stated limit, per-user scoping,
chips + save control on /explore; EXPORT deliberately absent (data-export
trigger stands). (2) docs/13-T4-OTLP-SPEC.md — the WP-T4-SPEC mapping
contract (gen_ai.* dual-version → CallRecordFrame, content DROPPED at the
door, agent/RAG/k8s dimensions as tags, honest per-detector T4 coverage
table, build estimate 3-5 days as its own future approval). QUEUE
UNCHANGED per PLAN-TAAS §3: launch → WP-CC-LINK → WP-PIPELINE-UI →
WP-CLOUD-T2 (C-A Azure → C-B Bedrock → C-C Gemini) → WP-COPILOT-AGG;
M-FLY-0 (A1+A2) may interleave. DEPLOYED: v1.6.0 live 2026-07-23 (founder-approved; smoke in
CHANGELOG). R-F1 signed off and shipped same day (entry above).

### system-tester gate rounds 1-3 (2026-07-23) — FAIL → FAIL → PASS; the loop works

Sweep 1 FAIL: explorer denied history the dashboard claimed (bare audits —
findings, no aggregate rows) → fixed a228ad7 + cross-surface journey law.
Sweep 2 FAIL: (a) Act stage printed the VERIFIED count labeled "applied"
("0 applied" on an account with 1 applied fix) → now applied = verified +
still-measuring; customer-reported $ rendered separately per R-Q9. The
sweep's expectation that realized-$ join the verified figure was DECLINED
as contradicting the ruled R-Q9 law — recorded so future gates don't
relitigate. (b) "0 findings — clean" was an unscoped account-wide claim →
now "0 new findings — latest audit clean · N earlier findings in your
history — see Explore". (c) its open question confirmed REAL: the explorer
empty-state chooser ignored model/date/detector/severity/status filters →
every active filter now routes to "Nothing matches this slice". Fixed
21fde3d, tests pinned same commit. Sweep 3 PASS — all repro walks confirm
exact wording; one non-blocking observation parked: waste_trend widget
renders no $ figure on 1 day of data (plausibly the honest not-enough-days
state; outside this diff — pin with a targeted widget test on next touch
of that surface). Role ledger since creation: 3 sweeps, 6 findings, 5
real bugs fixed + test-pinned, 1 lawful decline, 0 found by the founder.

## R-SYSTEM-TEST + R-LIVE-DASH (2026-07-23) — the testing role exists now; first sweep found 3 real bugs

Founder order: "who is doing the system testing? why am I the one finding
mistakes?" Honest answer recorded in docs/10 amendment R-SYSTEM-TEST: the
diff-scoped gates share a product-level blind spot by design. Closed with
(1) tests/test_journeys.py — signs in, renders every app destination,
follows every emitted link, pins the no-landing-escape and live-dashboard
laws, runs on every commit; (2) .claude/agents/system-tester charter —
walks the milestone's journeys at every gate + post-deploy, judges the
WORDS on pages, not just status codes. FIRST SWEEP FOUND: (a) /upload
escaped the app shell (cookie-only auth resolution vs the app-wide shim —
aligned); (b) SEVEN dead /guide/* links live on the dashboard since V-D4g
(help-registry links to pages never written — guide_page() now synthesizes
them from the widget's own registry copy, single-source law, no dead links
by construction); (c) docs-site offered no way back to the app (founder
report — mkdocs nav gains "↩ Your dashboard"; in-app Documentation opens a
new tab). R-LIVE-DASH: no stale dashboard — the pipeline poll's landing
render emits HX-Trigger: audit-landed; all 9 widgets listen and refresh
once; idle = zero polling (tests pin listener count + header semantics).
PLAN-TAAS.md DRAFTED (awaiting approval): the "tokenomics as a service in
any environment" order mapped to the record — T4 OTel ingest, deployment
contract, R-AGNOSTIC cloud connectors (Azure OpenAI/Bedrock/Gemini),
Copilot AGG, Cursor/Lovable blocked-by-no-API truth; 5 questions incl.
promoting WP-CLOUD-T2. OPEN: PLAN-TAAS §4, PLAN-FLYWHEEL §6 rulings.

## R-ICON-ACTIONS + R-PIPELINE-LIVE (2026-07-23) — same-branch follow-up orders, both shipped + gated

Two founder orders after the M-EXPLORER gate round, on wp-report-explorer:
(1) R-ICON-ACTIONS — Sources rows compacted to an icon action cluster
(view/details/revoke) via new kit citizen `icon_action` (label REQUIRED →
aria-label+title; icon-only never unnamed), i-eye/i-trash sprite symbols,
.icon-btn role-token styles, danger-warms-on-hover; ux gate
PASS-WITH-NOTES, note actioned (F10 mobile 44px tap targets extended to
.icon-btn). (2) R-PIPELINE-LIVE — the W0 ribbon keyed states on widget
EMPTINESS (founder saw "Waiting" on Analyze beside 11 findings; root
cause: an unpriced audit empties spend_trend). Now metrics.pipeline()
computes states from the audit RECORD: idle = what ran (+clarity
"pricing pending"), in-flight = `live` A6 pulse ("Queued to run"/"Reading
your data"/"N calls read") with htmx self-poll every 2.5s that drops on
landing (idle dashboard = zero polls); clean audits report "0 findings —
clean" (ux f.1), previous report stays visible marked "refreshing". ux
gate PASS-WITH-NOTES, f.1 actioned. Tests: TestIconActions,
TestPipelineLive (5). Commits 1bf1b0b, bcaf367; full chain
lint+format+type+suite exit-0 on each.

## M-EXPLORER (2026-07-23) — FR-32 report explorer + R-MULTI-SOURCE, branch wp-report-explorer

Founder same-day orders: (1) R-EXPLORER — "client selects reports over all
history with filter options... still not implemented" → FR-32 promoted (PRD
amendment) and BUILT; (2) R-MULTI-SOURCE — "only one source can be connected
at a time, no option to select multiple llm accounts and switching to that
details" → per-provider connect block REMOVED (it was an implementation
shortcut, not R-Q5/Q6 law, and capped Team's 5 sources at 2), replaced by a
keyed one-way key-fingerprint dedup (same key twice = 409 naming the
existing label; pre-013 sources backfill on next pull); audits gain
source_id (additive migration 013); explorer gains a per-account selector;
Sources rows gain "View usage" deep-links. DECISIONS: overlap law "latest
audit wins per (day,model) bucket" (money-adjacent default, NOTES-sheet
derivation + test); findings de-dup on the R-Q9 (detector,route) key,
latest occurrence + seen-in count; unattributed pre-013 connected audits
stated in words on per-account views, never silently dropped. PROCESS:
ux-reviewer gated the mockup BEFORE wiring (FAIL → rebuilt on kit
vocabulary → PASS-WITH-NOTES; systemic --serif note parked as BACKLOG F17).
DISCREPANCIES OF RECORD: (a) tests/test_pricing_sync.py imported bare
`scripts` — collection breaks under the canonical `uv run pytest`; fixed
forward with the test_ops_scripts file-loader pattern; (b) the CI mypy gate
was RED at HEAD (19 pre-existing errors in 8 files, none from this
milestone) — closed with an annotations-only pass, zero behavior change.
FILE MAP DELTA: +services/dashboard/explorer.py, +web/routes_explorer.py,
+templates/app/explore.html, +design/mockups/explore-v1.html,
+migrations/013_source_attribution, +tests/test_explorer.py;
crypto.credential_fingerprint, pull backfill, source_audit/routes_sources
attribution+dedup, sources.html links, help_registry explore key, _shell
nav. OPEN AT THE TIME: PLAN-FLYWHEEL §6 rulings — since RESOLVED same day
by R-PROCEED and R-F1-SIGNOFF (see entries above); kept for the record.

### M-EXPLORER gate round (2026-07-23) — four gates, no FAIL

spec-guard PASS (7/7 clean; fingerprint confirmed one-way, migration
additive, traceability spot-checked). ux-reviewer PASS-WITH-NOTES on the
wired surfaces — f.1 FIXED: detector-label fallback removed, template
indexes the label map directly and the map covers options+rows, so a
missing registry key fails loud (T-HELP law) instead of leaking a raw id;
f.2 FIXED: unattributed copy now owner-phrased ("before we could tell your
connected accounts apart"); f.3 (has_any_history naming) + f.4 (i-reports
icon reuse) ACCEPTED — icon reuse is intentional until WP-PIPELINE-UI
ships its own runs page. cold-reviewer PASS-WITH-NOTES — f.1 FIXED
(overlap-law tie-break now (report_ready_at, id): same-timestamp audits
resolved deterministically, test_18), f.2 FIXED (findings de-dup tiebreak
(when, fr.id) — same-key rows can no longer vanish by DB return order),
f.3 FIXED (unattributed-audits warning bounded to the active date window,
test_19), f.4 FIXED (label suffix counts ALL provider sources incl.
revoked — revoke+reconnect can't mint duplicate labels,
test_revoke_then_reconnect_never_reuses_a_label), f.5 RECORD CORRECTED:
the c4dbefd chore was NOT strictly zero-behavior — three None-guards in
daily.py digest strings default an impossible-branch None to $0.00 rather
than crashing; accepted as fail-soft in an alert path, recorded here.
vv-engineer PASS-WITH-NOTES — both open items closed by main thread with
evidence: pricing/table.py diff is one annotation + format rewraps (no
formula/rate content, goldens untouched); full chain ruff+format+mypy+
pytest exited 0 under pipefail (pinned toolchain). Never-mask-pytest-exit
lesson re-learned twice this milestone: piping pytest through tail ate a
collection error AND an exit code — exit-code checks now run with
pipefail, no bare pipes.

## PLAN-FLYWHEEL drafted (2026-07-23) — AWAITING FOUNDER APPROVAL, no code

Founder order (train-on-entire-history / front gate / preventive
intelligence / customized per-client / filterable full-history reports)
broken down in PLAN-FLYWHEEL.md. Coverage audit finding: most of the order
is already SHIPPED (365-day backfill + back-dating, L0 labels, L3
deterministic forecast, observe-only alerts/digest) or trigger-registered
(T5 front gate — X-01/X-02 untouched); buildable gaps are L1 peer
benchmarks, L2 shadow threshold calibration, and a NEW report explorer
(proposed FR-32, parked as WP-REPORT-EXPLORER in BACKLOG). BLOCKER ruling
R-F1: "never used for training" is live verbatim on 5 surfaces (report
model.py:52, public shell, Terms, Privacy, docs-site) and test-pinned —
training/benchmark scope cannot start until the founder picks option
A/B/C (PLAN-FLYWHEEL §1). Eight numbered questions await ruling (§6),
incl. TE-5 amendment: Fable authors PRD/design, Opus implements, Sonnet
gates. Sequencing proposal slots new milestones AFTER the ruled queue
(WP-CC-LINK → WP-PIPELINE-UI); nothing already ruled moves. File map
delta: +PLAN-FLYWHEEL.md, BACKLOG.md (+WP-REPORT-EXPLORER), this entry.

## R-LIVE-PRICING + R-LIVE-AUDIT (2026-07-22) — autonomous pricing, live audit status — DEPLOYED

Founder ruling (verbatim): no human gate on pricing, cover leftover jobs, show
real-time status during auditing — "always manual looses the game." SUPERSEDES
the human-approval gate in R-PRICING-OPS / R-PRICING-AGENT (recorded PLAN §0.1).
DECISIONS: (1) "no human gate" done safely = automated validation replaces the
human, not blind trust. Source = the STRUCTURED LiteLLM model-prices JSON (the
feed R-PRICING-AGENT already trusted), NOT heuristic HTML scraping (providers
delete models from pages — the gpt-4o-mini incident's root cause). (2) A separate
machine-managed overlay `prices.auto.yaml` (gitignored, env-local, written by
ofelia on prod) is merged append-only over the hand-verified base; the base is
never touched; every auto row carries `source: litellm-auto`. A HUMAN base row
always wins a same-date tie (cold-review f.1). (3) Validation gates: four-rate
shape, plausible band, jump-guard holds swings >±60%, no-op skip, $0 never
written (cache 0 → input fallback). (4) `--cover-from-usage` scans usage for
unpriceable models, covers them, RE-AUDITS affected sources; two ofelia jobs
(pricing-sync-refresh daily 02:50, pricing-cover every 3h). (5) R-LIVE-AUDIT:
connect kickoff creates a queued Audit synchronously → live theater; worker
extracted to module-level `_process_first_pull` drives queued→processing→
done/failed (cold-review f.2). FILE MAP DELTA: +scripts/pricing_sync.py,
+tests/test_pricing_sync.py; pricing/table.py (overlay merge), source_audit.py
(finalize pre-created row), routes_sources.py (+_process_first_pull/_mark_failed),
_wizard_verdict.html (land on theater), daily_digest.py (sync FYI+alert),
ofelia.ini (2 jobs), .gitignore (overlay). GATES: vv-engineer PASS, cold-reviewer
FAIL→fixed→PASS. DEPLOYED 2026-07-22 (backup tokenops_2026-07-22.dump; app
rebuilt, ofelia reloaded, DNS healthz 200, prod feed reachable). First real
cover-from-usage priced gpt-4o-mini and re-audited the founder's source (now
priced, 0 findings = honest "no waste", not "unpriced"). No migration (head
e5b8c2f74a19 unchanged). No rate VALUES changed in base card. OPEN: two-reading
persistence for held swings is a BACKLOG enhancement (currently held one cycle,
surfaced in digest); legacy claude-3.x coverage is demand-driven via usage.

FOLLOW-UP (same day, empty-dashboard incident): founder reported the Overview
still all-$0 after the pricing fix. Root cause was NOT pricing — TWO bugs: (a)
connect_backfill_days was 30, but a read-only wide-window probe found the org's
real usage (2,264 calls: gpt-4o-mini/gpt-4o/gpt-4.1) sat in Mar-Apr 2026, so the
30-day window pulled a 35-call sliver → widened to 180 (config, env-overridable;
commit 41374c6); (b) the overlay lived in the container's ephemeral fs, so every
`up --build` wiped auto-pricing until the next cover run → moved to
PRICING_OVERLAY_PATH=/data/reports/.ops/prices.auto.yaml on the persistent
reports volume, proven to survive force-recreate (commit c98af0b). Prod remediation:
forced full re-pull (2,264 calls, Mar 24-Jun 30) + cover-from-usage priced all
three models + re-audit → latest audit spend $0.1732 over 26 days, 1 finding
(d2_missing_cache). The org's OpenAI spend is genuinely small (~$0.17); the
customer's real spend is likely Anthropic — connect-Anthropic nudge is a
follow-up. No gate needed (config + infra, no money-math logic change; full
suite green).

## R-FLYWHEEL L3 + FULL-HISTORY (2026-07-23) — forecast shipped, entire year priced — DEPLOYED

Founder direction: the moat is proactiveness/tokenomics per docs/12-FLYWHEEL
(already-documented design; NOT new scope — corrected my own scope-freeze
misread in-session). Founder picked "before-the-invoice forecast + anomaly
alerts" as the first rung. SHIPPED as deterministic-now L3: services/forecast
project_cycle() (month-end projection vs trailing-90d baseline, all money via
daily.spend_between), dashboard _forecast widget, daily-digest heads-up line.
Honesty Law enforced: prints basis, refuses to project below data thresholds,
holds the alert on a partially-unpriced BASELINE (false-alarm guard), flags
unpriced CURRENT-month usage as "understated" (cold-review f.1 — alert still
fires; understatement is conservative-safe). T-NFR-01 now guards forecast.py
(GUARDED_MODULES). GATES: cold PASS-WITH-NOTES (f.1 fixed, f.2 advisory
accepted), vv PASS-WITH-NOTES (import-guard + branch tests closed). Commits
01334e8, c925222, d5475dd.
FULL-HISTORY CHAIN (same day): backfill 365d re-pull found the REAL account —
46,868 calls / 23 models / Jul2025-Jun2026 (the 30d window had shown 35 calls).
Two coverage bugs fixed (commit after d5475dd): gap scan now checks
priceability at each bucket's USAGE date (was: today), and cover back-dates
COVERAGE_BACKDATE_DAYS=400 spanning the audit window (was 90 — covered-today
models left 2025 buckets unpriced; audit read $0.17). Honesty caveat recorded:
current feed rate applied across the window, provenance litellm-auto. RESULT
IN PROD: audit 36963bd0 = $96.87 spend, 46,868 rows, 86 days, 11 findings,
21.9% savings identified. 41 overlay rates written, 0 held. healthz 200,
pricing age 0 days. NEXT: founder connecting an Anthropic key is the highest
value step (their real spend is Claude-side).

## R-PRICING-FINAL-2 + R-DAILY-LOOP (2026-07-22) — dual-market pricing + the daily surface

Ratified after five founder amendment rounds (analysis in
launch/PRICING-INDIA-ANALYSIS.md + UNIT-ECONOMICS.md). Prices now: global
$19→$29 / $59→$99, India ₹499→₹999 / ₹14,999 flat, one-shots $500/₹20,000;
first-200 launch cohort PER MARKET, grandfathered, flip computed in code
(plans.launch_open counts Subscription rows; cancelled counts, failed-only
doesn't); one currency per view (viewer_currency: subscription wins, then
?ccy, then Accept-Language), no-mixing test-pinned; R-Q11 display_both
RETIRED. Daily loop: services/connectors/daily.py (digest + 50/80/100
budget stages on the existing soft_budget rule, AlertEvent-deduped),
tick() runs digests after audits, dashboard "yesterday" widget
(metrics.yesterday_spend, same rate math as source_audit — one formula,
three surfaces), migration 008 users.last_daily_digest_at (head
a9d24c8e7f31). Ops digest prints per-market cohort fill; runbook §3a
documents the hosted-page flip step (undercharge-only window). File map
delta: +services/connectors/daily.py, +tests/test_pricing_final.py,
+tests/test_daily_loop.py, +widgets/_yesterday.html, +migration 008;
plans.py rewritten (launch/cohort/currency machinery). Open question: none
— founder actions unchanged (payment links now created at LAUNCH prices).

## WIRING GATE CLOSED (2026-07-21) — ux PASS-WITH-NOTES · vv PASS-WITH-NOTES · cold PASS-WITH-NOTES

All gates ran on the settled diff 1d501bd..d4914fe (kit §3+§4 → §5 → §6 →
wiring). Note dispositions, all closed same-day:
- ux.1 billing badge fix unproven by stale screenshot → re-rendered against
  the current build with an assert: badge shows "Pro". Other ux notes were
  confirmations (hero rule clean in both moods, authority omission real,
  jargon law holds at depth (c)).
- cold.1 run_all stats["users"] silently changed meaning after the plan
  filter → renamed "watching_users" (schedule.py only consumes fired/errors,
  so the tick log never carried it — rename is belt-and-braces).
- cold.3 a future Applied button could ship without the ask (the shell
  handler skips confirm-less buttons silently, by design for Dismissed) →
  sweep test: any value="applied" control in ANY template must carry
  data-confirm (test_authority_laws.py).
- cold.2/cold.4: verified non-findings (HX-Target cannot cross users —
  _drawer_context re-checks ownership unconditionally; the one |safe wraps a
  hardcoded literal).
- vv.2 CARRIED DEBT (pre-existing, outside this diff): schedule.py 84.8%
  vs the 85% services floor (lines 91-94, 100-103, 111-112). Close
  opportunistically per the V-D10 slack rule; recorded, not chased today.
- vv confirmed: suite EXIT=0 under uv, total coverage 95.9%, pricing/rules
  untouched (CLAUDE.md rule 4 not triggered), money-math files at 100%.

## WIRING MILESTONE (R-LOOK-FINAL §4, 2026-07-21) — v15-ui-unify surfaces on the kit

All 7 pre-kit screens migrated onto the kit (findings, _finding_drawer,
_top_findings, alerts, sources, settings, billing); the allowlist emptied and
its ratchet retired — the no-hand-rolled-tables rule now binds EVERY app
screen. Kit grew what the screens proved they need: linkable sortable table
headers (SSR reorder links with the sort icon), surface span/id/aria-live,
empty_state secondary action, table cls passthrough, thead omitted when no
column is labelled, savings_hero cap=False for surfaces that already title
the figure. Funnel: the magic link itself now 303s to /dashboard (v1 landed
on /upload; test pins the actual link-click). No v1 URL ever moved — the
"legacy 301s" item resolves to that behaviour fix; nothing else to redirect.
Mood toggle in the topbar (aura at launch): pre-paint localStorage read, one
attribute swap, verified in Chromium that values swap and survive reload.

FOUND BY RENDERING, NOT REVIEW (playwright against the seeded preview):
1. The findings drawer's feedback form targeted #w-savings, which does not
   exist on /findings — htmx aborts on a missing target BEFORE the request,
   so EVERY verdict cast from that page silently recorded nothing (and §5c's
   ask never fired: htmx resolves the target before htmx:confirm). Fixed:
   the drawer targets itself; the route answers by HX-Target — refreshed
   drawer for the findings page, savings widget for the dashboard's form
   (signature moment intact). Route-level tests never saw it; they POST
   directly. Test now pins the HX-Target branch.
2. _savings.html and statements.html stacked money-hero + total-rule on ONE
   div — .total-rule is a standalone 3px element, so the 84px figure was
   squashed into the border: the double rule STRUCK THROUGH the verified
   total on the shipped dashboard. Both now compose kit.savings_hero; the
   stale duplicate .money-hero (84px) removed; tests pin one-declaration-
   per-money-class and forbid the class stack anywhere.
3. Billing's topbar plan badge rendered as an empty pill (route stripped
   plan from shell ctx); sources repeated the purpose line twice.
Confirm handler verified end-to-end on the real page: ask fires, decline
holds, accept records. Hero asset captured from the seeded account, sample-
data label baked into the pixels, 95KB (<120KB budget):
design/assets/hero-dashboard-sample.webp.

## §5 SERVER-AUTHORITY LAWS (R-DESIGN-TOKENS-2, 2026-07-21) — implemented

Audit result: sources/wizard/feedback/widgets/statements already re-checked
authority server-side (plan caps, ownership, signed report URLs, admin token);
billing upsells honestly. Fixed the four §5 violations found: (1) the kit's
data-confirm was a dead attribute — ONE delegated handler now covers both
transports (htmx:confirm + capture-phase submit) in app/_shell.html, verified
in real Chromium (4 cases: ask/decline/accept/no-attr); (2) Applied — the one
verdict that feeds the verified headline — now asks first with the consequence
in words; dismissed/not-relevant deliberately do NOT ask (confirm fatigue);
(3) sources.html revoke had no ask (settings.html did, inline) — both now use
data-confirm, inline onsubmit retired, a test forbids a second mechanism;
(4) alerts shipped the full rules form to Free, whose plan nothing watches
(dispatch only runs from the schedule tick; Free has no scheduled audits) —
the rules payload is now OMITTED for non-watching plans (honest upsell with
both currencies in its place, history stays), POST /alerts re-checks and 403s,
dispatch.run_all filters by the same plan_watches() rule, and the dashboard
alerts widget says "nothing is watched on this plan" instead of "checked
hourly". plan_watches is deliberately the PLAN capability, not read_only-
adjusted: dunning pauses scheduled audits only (Terms §6), so past-due Pro
keeps its rules armed. Tests: tests/test_authority_laws.py; test_alerts.py
run_all/page tests now model paying customers explicitly.

## §6 I18N KEY LAYER (R-DESIGN-TOKENS-2, 2026-07-21) — implemented

web/i18n.py + web/locales/en.json; t() is a Jinja env GLOBAL (imports drop
context, globals reach imported macros — proven by a render-through test).
The catalogue is a value sheet exactly like a mood: components reference
keys, a locale supplies values; en ships alone and a second locale must
arrive as a full reviewed sheet (Indic locales stay BACKLOG). The KIT's 18
chrome strings migrated now (hero cap, WHY/EVIDENCE/FIX/VERIFY headings,
tour, drawer default, Try again, Computing…); screen strings migrate AT
WIRING per the ruling's own wording. Missing key renders as its raw key
name — visible and greppable, never a 500 — and tests forbid it shipping:
every used key must resolve, no orphan keys, interpolations must format,
kit chrome literals are pinned OUT (tests/test_i18n_keys.py).

OPEN FOUNDER QUESTION (pre-existing, surfaced by this audit): the Pro blurb
sells "alerts and your monthly Savings Statement", but scripts/
monthly_statements.py builds AND EMAILS statements to every user including
Free (shipped in V-D6/V-D7, gate-passed). Terms only guarantee Free "archived
statements remain readable". Alerts are now plan-gated per the blurb;
statements were left as shipped — changing that is a product decision, not a
§5 fix. Flag for the production walkthrough: either the blurb overstates or
the monthly job over-delivers.

## V-D9 GATE CLOSED — ux PASS-WITH-NOTES · cold-reviewer PASS-WITH-NOTES (all 8 notes closed)

ux (3, closed): done-state cut to ONE line per R-MAGIC-CONNECT §1c (the
rest belongs on the dashboard); an orphaned hidden form removed from the
unreachable branch; the counts-only promise restated INLINE under the key
input — a reassurance one visual hop from the hand is half-read.
cold-review (5, closed): (f.1) validation ran BEFORE the plan check, so a
customer at their limit spent provider quota and six seconds to earn a 403
— now authorize-then-validate, with a test asserting the provider is never
contacted for a refused request. (f.2) a new user's row was discarded when
a bad key rolled the transaction back; user creation now commits
independently of the verdict. (f.3) no idempotency: a double-click bought
two connections and two first-pulls — now 409 with a re-check inside the
lock for the race. (f.4) the sample fixtures lived in tests/, absent from a
wheel, so /sample would have errored for real installs; they now ship
INSIDE the package and I verified it by building a wheel and listing its
contents rather than assuming. (f.5) sample_html claimed to render once and
did not — a public unauthenticated page re-running the engine per hit;
memoised, with a test that fails if the engine runs twice for three
requests. Suite green across 3 consecutive runs; ruff/mypy clean.
STILL DEFERRED (unchanged, founder's call): report web visual pass and
pricing-page Savings-Statement framing — the report shares its template
with the PDF and the golden-determinism tests.

## V-D8 GATE CLOSED

R-WIZ-ILLUSTRATION ratified and the ruling text amended in PLAN §0.1 +
PLAN-V15 (drawn diffable SVG replaces "annotated screenshot").
POLISH HALF: /sample (FR-16) runs the committed synthetic fixtures through
the REAL engine — ingest → price → detect → assemble — so every figure on
the shareable page is arithmetic the shipped detectors produced, not a
mock-up; it is deterministic run-to-run, needs no login, and carries a
banner saying plainly that the arithmetic is real even though the company
is not. /upload became the guided "Get your logs" flow: five routes in
(Connect wizard · Claude Code exporter · OpenAI · Anthropic · CSV), each
carrying its OWN counts-only promise beside the instruction rather than a
footer nobody reads (test asserts exactly five). Landing hero A/B per
R-PAINMOMENT: cookie-bucketed so a visitor sees one hero and never watches
it change mid-read.
FLAKE CAUGHT AND FIXED BEFORE THE GATE: the A/B made an EXISTING
R-GTM-CONTROL test intermittent (it asserts the control headline, now
shown ~half the time). Both that test and my own new one now pin their
variant explicitly — a coin-flip assertion has no place in a suite I call
deterministic. 3 consecutive clean full runs after the fix.
10 polish tests (T-POL-01..03 + sample determinism + hero arms);
sample.py 96.9%, routes_pages.py 100%; total 95.5%.
DEFERRED, stated honestly: the report web page's visual pass and the
pricing-page Savings-Statement framing are NOT done — the report shares
its template with the PDF and the golden-determinism tests, so restyling
it is a change I want gated on its own, not smuggled into a polish commit.

## V-D8 GATE CLOSED

R-NORMALIZE-AT-EVERY-DOOR + R-BATCH-SEND-ISOLATION recorded as permanent
laws, each naming the defect that produced it. WIZARD (R-MAGIC-CONNECT):
3 steps per provider — deep-link to the exact console screen with an
annotated SVG of the permission box (drawn, not a screenshot binary, so it
cannot rot silently in version control), live server-side validation, and a
done-state that promises nothing further. Three verdicts in plain words:
connected (read-only, states what we can NEVER see), can't-read-usage
(saves nothing), unreachable (R-WIZ-DEGRADE: SAVES the key, says so, offers
retry — a 6s timeout so a customer's first minute never hangs on a
provider's status page). On success an immediate pull+audit runs in a
background thread so the dashboard fills THIS session; a failure there is
invisible because the tick remains the guarantee. Wizard copy lives in the
help registry like every other string — and the T-WIZ-04 jargon guard
promptly caught MY OWN copy ("Anthropic admin keys page"), which is exactly
what the law is for; fixed the copy, not the test. Plan gate explains at
the START rather than failing after a paste. 12 tests; validate.py 94.7%;
suite green and deterministic; total 95.5%.
REMAINING for V-D9: /sample, guided get-your-logs tabs, landing hero A/B,
report visual pass, pricing framing — then the gates.

## V-D8 GATE CLOSED — cold-reviewer FAIL→FIXED · vv FAIL→FIXED (both re-verified)

The founder's instruction to attack money paths paid for itself twice over.
cold-review (6 findings, all closed): (f.1) email was normalised on CREATE
but not on LOOKUP, so a mixed-case address from checkout missed the lookup,
hit users.email UNIQUE on insert, and the provider retried forever — a paid
upgrade stuck in a permanent failure loop, invisible to the customer.
(f.2) the day-0 dunning EMAIL was unreachable: apply_event set status
past_due synchronously, so the sweep's idempotency guard always saw
stage == status and skipped — the R-Q11/12 "day 0 email" promise could
never fire in production, and my own test masked it by jumping to day 8.
Day 0 now emails at the transition. (f.3) the plan came from
provider-echoed metadata with no validation — "team" in a Pro checkout's
metadata escalated the tier; unknown values now keep the existing plan and
log. (f.4) I repeated the alerts mistake: emails sent inside a loop with
one commit at the end, so a later failure rolled back a rung whose email
had already gone — now committed per rung. (f.5) N+1 entitlement queries
per source → batched. (f.6) dead code in the billing route.
vv FAIL (4 findings, closed): (f.2, serious) every webhook-route test was
SKIPPING because the shared fixture has no webhook secret — the FR-27
dedup rail for subscriptions was never actually exercised. A dedicated
test-mode webhook app now runs all four; repo-wide skips are down to the
single environment-gated postgres test. stripe_link.py 77.8%→94.4% (its
whole subscription branch was untested while razorpay's was covered);
T-SUB-03 now exists by name for source counts AND scheduler cadence;
determinism double-run completed here (2 runs, identical, EXIT=0).
Total 95.6%. NEXT: STOP for founder review; V-D9 (polish + wizard) on go.

## V-D8 BUILT (founder GO 2026-07-22) — build record

ONE price config (services/payments/plans.py): every amount renders from
Settings, both currencies shown for paid plans (R-Q11), and a test greps
templates/routes for inline literals so a price change can never half-land.
Free is genuinely free — no price, no card, no scheduler, and the billing
page says "No card required" even on the row you are already on.
WEBHOOKS ride the EXISTING FR-27 rails: signature → timestamp tolerance →
event-id dedup, now shared by one-shot payments AND subscription events
(the dedup helper gained a structural protocol instead of assuming a
payment shape — it would have AttributeError'd on every subscription
event otherwise). Replay of a subscription event is acknowledged, never
reprocessed. DUNNING per R-Q11/12 exactly, as a PURE function of
(failed_at, now) so the rungs are testable without clocks: day 0 past_due
+ email, day 7 read_only, day 21 cancelled → Free. Two edges pinned: a
REPEATED failure must not restart the clock (or the ladder never reaches
day 7 and a failing customer keeps a paid plan), and a successful charge
clears it. Read-only touches exactly ONE capability — scheduled audits
pause; dashboard, reports and connections all stay, asserted. Cancellation
reverts to Free and deletes NOTHING (founder ruling verbatim; the email
says so). Scheduler now gates due audits on entitlements, which surfaced
that Free accounts must not get scheduled audits — the old scheduler
fixtures implied a source without a plan, which cannot happen (R-Q5/Q6);
fixtures corrected. 16 tests (T-SUB-01..05 + edges); plans.py and
routes_billing.py both 100%; suite green and deterministic; total 95.0%.
NEXT: gate verdicts, then STOP.

## V-D7 GATE CLOSED — cold-reviewer FAIL→FIXED · vv PASS-WITH-NOTES (note closed)

cold-review (3 findings, all closed): (f.1, promise-breaking) opting out of
the statement EMAIL also skipped archiving it, so Settings' own words —
"you can always read it here" — became false; the job now ALWAYS builds and
archives, and only the send is optional. (f.2) purge_one's guard missed the
upload_path=None + purged_at=None case, so an admin purge of a failed audit
that never stored a file would stamp purged_at and write an audit-log entry
claiming a deletion that never happened; the guard is now simply "no file,
nothing to purge". (f.3) the job's summary conflated opted-out with
already-sent — separate counters. WRITING THE f.3 FIX EXPOSED A LATENT
CRASH: the summary line still referenced a counter I had renamed, a
NameError that would have fired on every real run and that no
import-only test could see — now covered by a test that actually executes
main().
vv PASS-WITH-NOTES; note CLOSED: PLAN-V15's V-D7 entry still claimed alert
thresholds, which had shipped early in V-D5's /alerts page. Reconciled in
the plan (one editor per setting; Settings links to it) with T-SET-01
remapped to the tests that actually cover threshold persistence and
validation. Traceability rows added for WP-3b/4/5. purge.py 80.0% with
every remaining miss the pre-existing CLI main() — the carried debt,
unchanged. Suite green and deterministic; total 95.4%.

## V-D7 BUILT (founder GO 2026-07-22) — build record

Rulings recorded first: R-STMT-MONTH (V-D6 default ratified as law — single
compute(), a second copy forbidden forever), R-COVERAGE-DEBT (smtp/purge
carry; close in V-D10 only if slack), R-WIZ-DEGRADE (graceful degrade
approved for the wizard; T-WIZ-05 added to V-D9).
BUILT: one grouped Settings page (R-DESIGN §4f) — account facts, email
preference, connected sources with revoke, data controls, billing link.
Email: a statement-email toggle (migration 007, NULL = opted in) honoured
by the monthly job; the page states plainly that sign-in links and
report-ready mail always send, because they are how the product works.
DATA CONTROLS: "delete my uploads now" states its consequences in words
BEFORE asking, then requires the exact typed phrase; a near-miss deletes
nothing. REFACTOR FOUND A REAL GAP: the admin manual purge had drifted
from the scheduled one — it never deleted the FR-26 idempotency keys.
Extracted ONE purge_one() primitive now shared by scheduled, admin and
customer paths, which closes that gap and is pinned by a regression.
Purge is account-scoped (another account's uploads untouched, tested) and
idempotent. 10 tests (T-SET-01..03 + scoping/idempotence/primitive).
purge.py 77.5%→80.0%: every remaining uncovered line is the pre-existing
CLI main(), i.e. exactly the debt the founder ruled to carry — no new
uncovered code. Suite green and deterministic; total 95.4%.
NEXT: gate verdicts, then STOP.

## V-D6 GATE CLOSED — cold-reviewer FAIL→FIXED · vv PASS-WITH-NOTES (note closed)

vv: coverage TOTAL 95.4%, statements/build.py AND dashboard/savings.py both
100% (money-math floor met), T-STMT-01..03 verified non-trivial, the
month-credit default confirmed recorded in the SAME commit, migration chain
001→006 intact, equiv_spend confirmed written by both producers, and the
hand derivation independently recomputed (750/300/75/600 — matches).
Note CLOSED: my new regression loaded the monthly job through a
CWD-relative path, so it could fail when pytest ran from elsewhere — now
repo-relative via Path(__file__), proven by running the file from /tmp.
STANDING DEBT REPORTED, NOT SILENTLY FIXED (pre-existing, untouched by this
diff): services/mail/smtp.py 83.8% and services/lifecycle/purge.py 78.9%
are below the 85% services floor — v1 code, outside V-D6 scope; founder's
call whether to close them now or carry them.

## V-D6 — cold-review record

cold-review (4 findings, all closed): (f.1) pending_count was NOT
period-scoped while verified was, so July's statement could report a fix
applied in June as "awaiting confirmation" — the artifact contradicting
itself. Pending now belongs to the month the fix was APPLIED, verified to
the month an audit PROVED it. (f.2) _month_bounds closed at 23:59:59 while
compute() matched on year/month, so an audit in the final second of a month
was dropped from build()'s own query — a statement could print "No audit
ran this month" above a verified figure sourced from exactly that audit.
Both now share one exclusive [start, next-month-start) bound. (f.3)
POST /statements/{period}/send parsed the path segment with int() — "2026-13"
and "abcd-ef" were uncaught 500s; now a 400 via one validated parser.
(f.4) the monthly job had no per-user isolation, so one rejected mailbox
would silently cost every later user that month's statement. Regressions
added for each. savings.py AND statements/build.py both at 100%; suite
green and deterministic; total 95.4%.

## V-D6 BUILT (founder GO 2026-07-22) — build record

Inherits R-Q9 wholesale as ruled: VERIFIED-only headline (and subject),
identified + customer-reported in their own labelled sections that are
never summed with it, a provenance stamp per audit, and the FR-30
equiv-spend line verbatim when any audit in the period could not assume
metered billing — which required persisting audits.equiv_spend (migration
006) from both producers, since the flag lived only in the report model.
MONEY-MATH DEFAULT RECORDED (NOTES): R-Q9 does not say which month a saving
lands in when the fix ships in one month and the proof arrives in the next
— credited to the month of the audit that PROVED it, because a statement is
archived and emailed, and crediting the application month would mean
restating an artifact already in someone's inbox. Implemented as a `period`
filter inside the ONE compute(); a second copy of the formula would be a
money-math hazard. Archive law: one row per user per month, a re-run
refreshes a DRAFT, a SENT statement is frozen (test asserts the body does
not move even when the figures do); send is at-most-once like alerts, with
resend delivering the archived artifact unchanged. Statements page + detail
+ resend; monthly ofelia job (1st, 06:00 UTC); Savings statements earns its
nav entry (it ships). 9 tests incl. hand-derived arithmetic; suite green
and deterministic, coverage 95.3%. NEXT: gate verdicts, then STOP.

## V-D5 GATE — cold-reviewer FAIL→FIXED, vv FAIL→FIXED; both re-verified, awaiting founder review

cold-review (4 findings, all closed): (f.1, the serious one) the
savings-realized form posted verdict="{{ verdict or 'applied' }}", so a
customer typing a figure they saw on their own bill would silently mark the
finding APPLIED — feeding R-Q9's verified headline with a decision they
never made. The figure now rides WHICHEVER verdict they explicitly click
(three submit buttons, no defaulted hidden field). (f.2) the at-most-once
claim was false: the commit sat at the end of the per-user batch, so a
later send failure rolled back an event whose email had already gone —
each event now commits before its own send; the trade-off is stated in the
test (a failed send is a MISSED alert, never a duplicate). (f.3) threshold
truthiness read a deliberate 0 as "unset" — now `is not None`, so "alert me
on any spend" works. (f.4) the alert stage could kill a tick whose pulls
and audits had already committed — now isolated like every other stage.
vv FAIL (2 objective gates, both closed): dispatch.py was 64.7% (run_all's
loop never exercised directly) → 100% via a real per-user test incl. error
isolation; T-FB-01/02 existed as behaviour but carried no test IDs, so
traceability was fiction — now labelled in place with an ID map in
PLAN-V15. Also fixed a mypy narrowing error my own run caught. Suite green
and deterministic across runs; total coverage 95.1%.

## V-D5 BUILT (founder GO 2026-07-22) — build record

WP-3b: four rules per the ruling (spend spike DoD, waste above target, new
HIGH finding, soft budget), each evaluated against audits the customer
already has, each message leading with the NUMBER and naming its audit.
OBSERVE-ONLY is enforced, not just asserted: T-ALR-05 parses the alerts
package with ast (docstrings stripped, so prose naming the forbidden verbs
does not self-trip) and fails on any enforcement-shaped code; a second test
asserts no alert body claims we paused/blocked/capped anything. Dispatch
records the AlertEvent BEFORE sending so a mail failure cannot re-fire the
same alert (at-most-once beats at-least-once when the payload is customer
email); one alert per rule per audit. Delivery rides the existing adapter
(new `alert` method on the protocol + both adapters). Hourly connector tick
now evaluates alerts right after audits land, so a new finding reaches the
customer in the pass that found it. /alerts is a grouped settings form
(familiar shape, unparseable input falls back rather than erroring) with a
20-event history. PREVENT ribbon stage now reads real armed-rule state and
Alerts earned its sidebar entry — it ships, so it appears (no-promises law).
L0: the drawer gained the optional savings-realized input, labelled
customer-reported and stated as never touching the verified headline
(R-Q9). Suite green exit-code-checked; ruff/format/mypy clean.
NEXT: gate verdicts, then STOP.

## V-D4 + V-D4g GATE CLOSED — ux PASS-WITH-NOTES · cold-reviewer FAIL→FIXED→re-verified · vv PASS-WITH-NOTES

ux (3 notes, all closed): Prevent ribbon stage was static placeholder text —
the "coming soon" the shell forbids — now renders REAL armed-rule state
("Not set up" at zero); sortable headers were a false affordance, now do
real server-side sorting via SSR links; severity/confidence render as words.
cold-reviewer FAIL (6 findings, all closed, commit 362dee0) — THREE were
money-math defects that would have inflated the customer-facing headline:
(R1) weekly audits re-emit an unfixed finding with a fresh feedback row and
the old code summed them, billing the same saved dollars every week — now
ONE credit per route against the EARLIEST applied feedback; (R2) a route
vanishing from a later audit was credited in full even if the feature was
simply retired — now a disappearance counts only when call_aggregates prove
the route still carried traffic, else pending; (R3) the same finding could
book as both identified and verified. Enabling fix: findings.route persisted
by BOTH producers (migration 005) — "same detector and route" was otherwise
uncheckable. Also fixed: drawer showed a stale null verdict so an applied
route invited re-applying (the R1 trigger), overdue audits collapsed to
"today", malformed help placeholders could 500 a page.
PROCESS NOTE (mine): the first vv gate FAILed on a "non-deterministic
suite" — I had launched gates and then edited the same files, so it sampled
half-applied states. Gates review a FIXED diff; re-run on the settled tree
gave PASS-WITH-NOTES with determinism independently confirmed (2 runs, 280
tests, identical, EXIT=0). vv's coverage note (anthropic_usage 53.2%,
pre-existing from M1) closed too: fetch-path tests bring it to 95.7% and the
suite total to 95.1%. Money math savings.py 100%. NEXT: STOP for founder
review per order; V-D5 (alerts + L0 deltas) on go.

## V-D4 + V-D4g BUILT (founder GO on mockup v3, 2026-07-21) — build record

Founder v3 verdict: all three surfaces PASS, GO to wire; digest arrival
CONFIRMED. BUILT: R-Q9 verified-savings service (money math — 6 exact-value
goldens + NOTES derivation; the >=7-day gate reads a NEW audits.
observed_days column persisted by BOTH audit producers, since the rule was
otherwise unenforceable); metrics module (one function per widget, each
carrying its own provenance stamp); app shell (stage-grouped sidebar, only
shipped modules, freshness topbar, section purpose lines from the
registry); 6 widgets each independently htmx-refreshable at
/dashboard/w/<key>; pipeline ribbon from real state; findings table with
row->drawer expansion (punch-list item 2 DONE) where the drawer is depth
(c) in the fixed why/evidence/fix/verify/methodology order and carries the
detector id (punch-list item 1 DONE — headline depth is plain language,
test-enforced); L0 feedback capture that swaps the savings headline back in
(the applied-fix-flows-into-the-number moment); guided tour (vanilla JS,
5 steps, server-persisted dismissal, replay from Help); YAML help registry
as the single source for popovers + Guide + purpose lines with thresholds
rendered from live Settings; vendored htmx 2.0.4 + static mount (no CDN,
provenance in web/static/VENDORED.md); design-asset drift tests pinning the
shipped CSS/sprite to design/. Migration 004 additive. Suite 122 green
exit-code-checked, ruff+format+mypy clean. NEXT: gate verdicts, then STOP.

## R-CLARITY RECORDED (founder 2026-07-21) — designed developer depth + familiarity principle; still NO mockup round

Addendum to R-PERSONA in PLAN §0.1 + PLAN-V15. (1) Depth (c) on every
finding renders a FIXED order: why flagged (rule + threshold values) →
evidence table → the fix (copyable) → verify (what the next audit shows)
→ methodology link. Help-registry schema per detector therefore becomes
plain/technical phrasing + why/fix/verify + methodology_url; thresholds
render FROM Settings so help text cannot drift from config. New tests:
T-HELP-05 (full triple per detector), T-HELP-06 (thresholds live, not
hard-coded — changing a threshold changes the help text), T-HELP-07
(purpose line per sidebar destination). (2) FAMILIARITY: Stripe/Datadog/
Grafana grammar — filters top-left, time-range top-right, row→drawer,
aria-sort headers, breadcrumbed flows, grouped settings forms; novelty
budget spent ONLY on the pipeline ribbon + double rule. ux-reviewer
charter gained checks 9-11 (familiarity, developer-depth order,
section purpose lines). (3) Every sidebar destination opens with one
plain "what you do here" sentence from the registry. Mockup v3 unchanged
— founder verdict remains the only gate on wiring.

## R-PERSONA RECORDED (founder 2026-07-21) — three-depth law; NO new mockup round, v3 verdict still the gate

Design law recorded in PLAN §0.1 and PLAN-V15 (applies to V-D4/V-D4g/V-D9
as copy/structure discipline, not a new milestone): every surface reads at
three depths (owner headline in plain words with a money number · manager
context with provenance in words · engineer expander with evidence,
detector params, methodology); JARGON LAW — detector identifiers never at
headline depth, help-registry YAML carries both phrasings per key
(T-HELP-04 added: a headline-depth string containing a detector id fails
the test); Guide pages open with "who this is for" (Owner · Engineer ·
Both); architect lens (per-agent/pipeline/knowledge-base attribution)
REGISTERED NOT BUILT on BACKLOG — arrives with T4 span data; no
persona-forked dashboards, one shell three depths, Savings Statement stays
the owner artifact and the report PDF the shared one. ux-reviewer charter
amended with checks 5-8 (three depths per surface, jargon auto-finding,
audience tags, no forked views). Mockup v3 is UNCHANGED and remains the
open gate.

## MOCKUP v3 (R-DESIGN-V3) GATED — ux PASS-WITH-NOTES, all 4 notes closed; FINAL round, awaiting founder verdict → wiring

R-DESIGN-V3 recorded (PLAN §0.1); V-D4g added to PLAN-V15 as the
founder-accepted +1-day guidance package with T-HELP-01..03. DELIVERED
design/mockups/v3/{overview,findings-table,first-run-tour}.html +
design/icons.svg (22-symbol self-hosted stroke sprite, no emoji/icon
font) + v3 CSS layer (icons, stat chips, sortable table, help popovers,
tour spotlight, breadcrumbs, density pass: h1 22px, 15px/600 widget
titles with icons, 84px hero, tightened chrome). REAL charts: spend =
area with gridlines + $ axis + date axis; waste% = line with 25% target
band; sparklines inside chips — zero placeholder boxes. GUIDANCE: 5-step
tour (step 1 spotlighting the ribbon, Next/Skip, progress dots),
per-widget "?" popovers (what it shows · where the number comes from in
words · what to do · Learn more) from a single YAML registry at build,
HELP sidebar group, breadcrumbs stating each step's purpose in a
sentence. ux gate v3: PASS-WITH-NOTES, ALL CLOSED — f.1 one canonical
finding title across table row + expanded card + overview; f.2 trend
widgets gained their own next actions; f.3 "requires logs" moved to a
neutral badge (red reserved for real waste); f.4 un-carded ribbon
confirmed deliberate in-file. Contrast AA-clear on all new chrome
(sev chips 5.9-6.4:1, axis labels 7.2:1, target label 5.4:1).
NEXT: founder verdict on v3 → wiring begins (V-D4), remaining polish as
inline notes, no further mockup cycles.

## SUPERSEDED — mockup v2 (R-DESIGN-SHELL) — ux PASS-WITH-NOTES, 4 notes closed

R-DESIGN-SHELL recorded in PLAN §0.1 (app shell, widget grid, pipeline
ribbon, determinism-as-design; zero scope/date change). Built
design/mockups/v2/{overview,first-run,findings}.html on shell components
added to wa-design.css. SHELL: sidebar grouped MONITOR/CONNECT/ACT/
ACCOUNT/ENGINEERING — only shipped modules, zero "coming soon" (grep
clean); topbar = product name · page · plan badge · freshness stamp ·
account. OVERVIEW: W0 ribbon (INPUT→ANALYZE→REPORT→ACT→PREVENT from real
state) + W1-W8 widgets, each with title, "What this tells you" line,
provenance stamp, designed empty state. FIRST-RUN renders in the SAME
shell with every widget in its guided empty state (no shimmer, no invented
numbers — R-Q9 held). ux gate v2: PASS-WITH-NOTES, all 4 closed — f.1
non-money stats got .stat-lg so nothing outranks a dollar figure; f.2 W1
hero gained its own next action; f.3 topbar now carries the product name;
f.4 overview names its delight. Contrast measured AA-clear on all new
pairs (sidebar active 11.1:1, ribbon 9.9:1, provenance 6.4-7.4:1).
NEXT: founder three-second re-review of v2 → GO → V-D4 wiring.

## SUPERSEDED — R-DESIGN v1 mockup set (single-page dashboard) — ux PASS-WITH-NOTES, 3 notes closed

Consolidated order 2026-07-20 applied: Part 1 verified verbatim-identical
to the prior approval (already executed — skipped); R-DESIGN + ADDENDUM
recorded in PLAN §0.1, ux-reviewer charter amended (three-second rule +
delight/contrast/reduced-motion checklist + banned list); R-AGENTIC-
DIMENSIONS + R-RAG into docs/12 (T4 mapping preserves agent + vector-DB
span dimensions; policy grammar = the platform's "autonomous mode"
definition; L3 fires mid-cycle); R-APIKEYS build detail on the BACKLOG
trigger; R-AGNOSTIC expansion law in docs/12 + BACKLOG queue (Gemini,
Bedrock, Azure-OpenAI T2; Copilot AGG); dark-mode + RAG-pack BACKLOG
lines. MOCKUPS (frontend-design skill read first): design/wa-design.css
(tokens: paper neutrals, deep-teal accent chosen once, serif tabular
money, 2-4 tier crisp shadows, count-up/pipeline/spring motion with
reduced-motion neutralization, print styles) + design/mockups/
{dashboard,finding-card,first-run}.html. Signature: the accountant's
DOUBLE RULE under verified totals. ux-reviewer mockup gate:
PASS-WITH-NOTES — f.1 estimate-amber contrast 4.10:1 → darkened to
#7a5500 (AA); f.2 first-run's deliberate no-number state annotated as the
R-Q9 exception; f.3 delight de-scoped to exactly one per surface. All
closed same day. WIRING BLOCKED until founder three-second review of the
mockup set (R-DESIGN §5).

## G-V1 GATE COMPLETE — vv PASS-WITH-NOTES · cold-reviewer PASS-WITH-NOTES · spec-guard PASS-WITH-NOTES (all notes closed same day)

vv: suite green EXIT=0 pinned toolchain; 93.9% total; money-math same-
commit discipline verified (07e70e6, 12ea389); notes CLOSED — T-AGG-06
empty/clean false-positive guard committed, T-AGG-07 covers findings.py:99
(money-math 100% restored) [77ab0b6]. cold-reviewer 4 findings CLOSED
[b186ac8]: f.1 connect plan-cap race → user-row lock; f.2 dead
delete-by-new-id removed + append-history semantics documented (weekly
audit series IS the dashboard trend history; FR-21 derived-aggregates
clause); f.3 unpriced-skip semantics documented (FR-28 surface; unpriced
d1 target skips conservatively — engine stays pure); f.4 provenance
latest-wins documented (PullStats log is history). spec-guard notes
answered in-record: n.4 the never-logged guard IS executable
(test_v15_foundations.py::TestKeyEncryption::test_03, its grep missed the
method name); n.6 future-WP schema in V-D1 is per PLAN-V15 §1 V-D1
foundations (inert, test-covered). M1 STOPPED for founder review per
approval order; V-D4 dashboard next on go.

## v1.5 M1 BUILT (V-D1..V-D3, branch v15-m1) — at G-V1 gate

Foundations: 7 additive tables (migration 003), HKDF/Fernet source-key
encryption (decrypt only in pull path; revoke deletes ciphertext;
never-logged guard T-KEY-03), v1.5 config knobs + .env.example. WP-1: T2
aggregate estimators per R-Q1 (d1/d2/d3 variants, hand-derived goldens
13.365/4.32/2.16/1.296/3.69, derivations in golden NOTES same commit;
d4/d5/d6 NEVER emit on aggregates — labeled upgrade-path coverage rows);
OpenAI+Anthropic usage clients (fixture-driven, documented mapping,
injectable SupportsGet); pull.py idempotent upsert with PullStats summary
logged every pull; source_audit.py account-tier reports (tier+coverage
keys added to report JSON, T-REP-03 updated same commit; row_count = Σ
provider calls; equiv_spend=false); connect/revoke SSR UI (plan-gated
R-Q5/Q6, key never rendered). WP-3a: ofelia hourly connector-tick
(no-overlap) → due daily pulls + weekly audits from last_*_at stamps,
re-entrant, per-source error isolation. Suite 96 green exit-code-checked;
ruff+mypy clean. ACCEPTED DEFAULTS (per approval order; guardrails
honored): Q2 backfill 30d; Q3 ofelia-tick→due-queue; Q4 cryptography dep
+ httpx promoted dev→runtime (unasked, recorded); Q10 alert threshold
knobs seeded (spend-spike DoD 30%, waste target 25%; delivery lands
V-D5); money-math defaults (D2-agg target = account's own best bucket
share; D3-agg needs ≥3 buckets) recorded in golden NOTES. DEFERRED to
their milestones: Q7 statement anchor (V-D6), Q8 savings-realized
enforcement (V-D5), Q13 htmx vendoring (V-D4), Q14 FR-31 retention
(V-D4), Q15 hero A/B (V-D9), Q17 early-access untouched, Q18 day-45
metric = MRR + one-shot combined (paperwork). Nothing escalated: no
default touched X-scope/FR-22/honesty law. NEXT: G-V1 verdicts, then
STOP for founder review; V-D4 dashboard after. Walkthrough (R-WALKTHROUGH)
scheduled day 3 — founder held to it.

## GRAND CONSOLIDATED ORDER v2 APPLIED (founder 2026-07-20) — STOPPED at PLAN-V15 approval gate

Part A: vision recorded verbatim PLAN §0.0. Part B: docs/12-FLYWHEEL.md
created (T1-T5 one-contract tiers, LLM-free label factory, L0-L4 honesty
law, four moats verbatim, R-STANDARDS); docs-site Standards page written
promise-free, shipped LIVE to docs.tokenops-cost-auditor.com. Part C: verified
already applied in 82024a1 (digest set+proven, NFR-04 amendment+VPS
benchmarks live, ledger ritual audited) — NOT redone; digest-arrival
confirmation pending founder inbox 03:00 UTC. Part D: recorded in PLAN
§0.1 + PRD Amendments; docs/01 amendments applied (X-05 relaxed to
SSR+htmx for v1.5; FR-22 extended to connector/streamed tiers; FR-31
added) with traceability rows same commit. R-CONNECT §4 + R-PAINMOMENT
notes updated (polish/onboard now delivered inside v1.5 WP-7).
FIRST TASK DONE: PLAN-V15.md written — 10 milestones over 14 days,
4 gates (G-V1..4), ~40 new test IDs, 18 numbered ambiguity questions,
risks. HARD STOP honored: no application code; awaiting founder approval
of PLAN-V15 + rulings on its §4 questions.

## D13 FOLLOW-UP RULINGS APPLIED (founder 2026-07-20)

(1) DIGEST_TO=lokesh@tokenops-cost-auditor.com set on the box, app recreated; manual
digest run SENT (mail.sent logged) — it surfaced a real NFR-08 alert ("no
backup dump found"), so the backup job was run manually (pg dump 4.0M +
reports tar 5.6M) and the digest re-run is alert-free; scheduled digest
03:00 UTC daily. (2) NFR-04 founder amendment recorded in docs/01 (bound
restated <=11 min/660s on the 4-vCPU class; VPS measured 624s — honest
number published, spec amended, never the reverse); docs-site performance
page gained the production-hardware section (624s/2.25GiB single; 34m20s/
5.14GiB 2x-concurrent; Contabo spec stated) and was REBUILT AND SHIPPED to
docs.tokenops-cost-auditor.com (live-verified); traceability NFR-04 row updated same
commit. (3) Ledger row 2 ritual audited: tick applied only AFTER the
founder's explicit VERIFIED message, log line signed in the same commit
(7112519) — stands; offer open to revert to pending if the founder wants
row-1-depth independent re-pricing added.

## R-PAINMOMENT APPLIED (founder 2026-07-20) — trigger-moment GTM; thread hook now bill-shock-first

PLAN §0.1 ruling recorded. launch-assets-DRAFT: Asset 1 post 1/ rewritten
to open with the bill-shock scenario (category label dropped from the
hook; defect story still leads the body — checklist line updated); new
"Distribution — trigger-moment targeting" section (search-and-reply on
bill complaints with the free audit offer, model-release-week timing,
hook discipline). Figure inventory / rails / FR-23 untouched — draft
remains APPROVAL-GATED. Landing hero A/B ("Just got an AI bill you can't
explain?" vs current) parked as a polish-time task — R-LAUNCH-POLISH
contents still not received. No product change made, per the ruling.

## R-CONNECT APPLIED (founder 2026-07-19) — WP-P2-AGG promoted to Connect flows; WP-COLLECTOR registered

Paperwork recorded idempotently: PRD Amendments entry (docs/00), PLAN §0.1
ruling block, BACKLOG WP-P2-AGG rewritten as PROMOTED (Connect
OpenAI/Anthropic, key handling encrypted/revocable/never-logged, UI parity;
layers b/c stay Phase-2) + WP-COLLECTOR section (pipx watcher, UAT-D5 dedup
law, counts-only, FR-26 idempotent ship). X-01/X-02 rationale recorded (in-
path components live in customer VPC post-trust). Launch-claims check:
grep of launch assets + web templates shows ZERO Connect references —
"honestly absent" already holds. Build does NOT start until the R-CONNECT
§4 sequence completes; R-LAUNCH-POLISH and R-ONBOARD contents NOT YET
RECEIVED — awaiting founder text before any polish/onboard work.

## D13 PHYSICAL DEPLOY — LIVE at https://tokenops-cost-auditor.com (founder GO 2026-07-19; two defects found+fixed)

Deployed via provision.sh one-command path to founder's Contabo VPS 4
(4 vCPU / 7.8 GiB; hardening ran FIRST per founder order: keys-only, ufw,
fail2ban). DNS apex+www+docs all serve with Let's Encrypt TLS; www 301s to
apex; docs-site (new Caddy block + provision step 4c build+rsync) serves
at docs.tokenops-cost-auditor.com; Postmark SMTP live (mail.sent verified to founder
Gmail); payments env-gated OFF. DEFECTS: (1) smoke's https://localhost
probe has no Caddy site under a real DOMAIN → --resolve SNI probes
(d33263b). (2) SEV: uvicorn multiprocess supervisor 5s keep-alive ping
replaced CPU-saturated workers → in-flight audits orphaned stuck-in-
processing ("Child process died" ×2 at t≈21min and t≈90s; OOMKilled=false;
ping(timeout=5) confirmed in installed uvicorn source; workstation cores
masked it, K-2 honored: 2 failed measurements → root-cause → ONE fix
attempt). FIX: --workers 1 (no supervisor exists; NFR-13 governs audit
concurrency) 8bd96a6, runbook §1 same commit, tag d13-live.1. POST-FIX
RE-VALIDATION PASS: 2×195MB/1.3M-row concurrent 34m20s wall, peak app
5.14 GiB + pg 150 MiB of 7.8 GiB, zero deaths (123 samples); single 1M
624s peak 2.25 GiB; F1 upload→done→web report 200→PDF valid; perf audits
purged. VPS ≈ 7-12× slower than workstation refs — completes correctly;
MP-6 docs still cite workstation numbers with machine spec stated (VPS
row = founder call). OPEN: DIGEST_TO unset; stuck-audit auto-recovery
parked in BACKLOG (admin rerun is the manual path, proven today).
ops-engineer GATE RE-RUN on the deploy diff + live endpoints: PASS —
topology/secrets/cron/runbook§2 all conform, workers-1 matches runbook §1
same-commit, live healthz/landing/docs/www verified externally; sole note
non-blocking (DIGEST_TO founder decision).

## SELF-AUDIT LEDGER ROW 2 — VERIFIED (founder tick 2026-07-19)

2026-07-19 run over all project sessions (130 files): dedup rows_in=3459
unique_out=1478 duplicates_dropped=1981; 1,478 unique calls, $512.92
API-equiv observed, $1,525.61/mo est. waste (29.7% of $5,129.24/mo),
findings {d3_prompt_bloat: 11, d6_chatty_loop: 3}. Machine checks printed
back and accepted: headline == Σ14 findings exactly; spend cap not
engaged; equiv_spend flag true; export duplicate request_ids = 0.
Founder VERIFIED same day — name in ledger row, verification log line in
pricing_golden_NOTES.md (golden discipline). 2/3 verified rows; trendline
stays MEASUREMENT-PENDING until row 3. Trend vs row 1: 1,340→1,478 calls,
30.3%→29.7% — stable. Report JSON archived (gitignored) at
self_audit/reports/2026-07-19_report.json.

## PLATFORM SKELETON CREATED (R-PLAT-DESIGN-EARLY; v1 untouched, migration timing unchanged)

Sibling repo ~/Desktop/witaura-ai-agentic-engineering-governance-platform @ f677161: docs/platform/
{ARCHITECTURE (v1.0 verbatim), DEPLOYMENT-CONTRACT, MIGRATION-WP-PLAT-0}
+ design READMEs for 5 packages / 4 apps / exporters / deploy / ops +
commented uv-workspace stub. ZERO product code moved; no CLAUDE.md there
(ONE-harness rule — migrates at WP-PLAT-0). Migration design maps EVERY v1
module to its target, fixes dependency rules, and defers exactly three
seams to founder ruling at migration time (SEAM-1 config split — recommend
plain-value params; SEAM-2 ratelimit → app; SEAM-3 app tables stay in
auditor until a second app needs the account model). Acceptance gate =
existing byte-identical-goldens tests; history-preserving merge planned so
the founder-authored commit log survives. TokenOps production pendings:
unchanged, founder-only (VPS deploy / UAT-2 / launch approval / post).

## D14 GATES COMPLETE — spec-guard final sweep PASS-WITH-NOTES, ux re-check PASS-WITH-NOTES

The program's last two gates ran pre-launch so D14 reduces to founder
actions. spec-guard FINAL SWEEP: PASS-WITH-NOTES — 8-row traceability
sample verified independently (FR-01/22/23/26/30, NFR-01/07/15 all cite
existing tests), import-guard EXIT=0, FR-22 confirmed via toolchain (T-LIF-04
+ exporter no-text tests), launch drafts figure-inventory-clean with both
rails + FR-23 verbatim, stats policy clean, ledger page leaks nothing
(MEASUREMENT-PENDING, 1/3 verified). Notes closed: FR-30 date is the
founder's IST ruling date (correct as given); X-scope full-surface re-grep
run in main thread — only internal parser MODULE names match, no SDK/proxy/
gateway/SSO/SPA markers anywhere. ux-reviewer scoped re-check (R-GTM-CONTROL
c): PASS-WITH-NOTES — hero/CTA-hierarchy/coherence clean; note FIXED
same-day: early-access support line tightened to promise-free copy ("The
audit is step one. Leave your email for early access."), tests EXIT=0.
EVERY GATE IN THE 14-DAY PROGRAM IS NOW CLOSED. Remaining = founder only:
VPS deploy → re-validation → CHANGELOG; UAT-2 send/waive; launch-asset
approval + URL fill; post.

## D14 PREP — launch drafts + UAT-2 kit ready (everything remaining is founder-action)

Traceability self-check CLEAN pre-D14: every docs/01 FR/NFR has a matrix
row, zero orphan rows, all DOC-column targets exist as pages, every cited
test family present in tests/. UAT2-KIT.md at repo root: copy-paste partner
email (FR-23 verbatim, counts-only assurance), evidence-recording template,
the two docs/05 §5 exit checkboxes — closes the vv gate's open finding the
moment the founder sends it and records the result.
launch/launch-assets-DRAFT.md: 8-post thread + HN post, APPROVAL-GATED —
figure inventory restricted to the verified ledger row + approved corrected
UAT-1 set, both rails verbatim wherever our numbers appear, attributed
stats only, defect narrative leads (228% + UAT-D5 refusal), FR-23 verbatim
in the pricing post; approval checklist at the bottom. REMAINING = founder
only: (1) VPS/domain/SMTP → one-command deploy (deploy/tf or provision.sh)
→ VPS re-validation → CHANGELOG; (2) UAT-2 send or waive ruling; (3)
launch-asset approval; (4) D14 go → spec-guard final sweep → launch.

## D11-12 vv GATE CLOSED — PASS-WITH-NOTES (after FAIL → fix → re-run)

vv-engineer re-run: PASS-WITH-NOTES. Full suite re-verified by the gate
itself with exit-code check (EXIT=0, 209 passed + 1 skip). Notes applied:
UAT-1 fix commit hashes pinned into the D11 paragraph (488b40c, 39a2d31,
8bed596); coordinator-side pass/fail extraction now exit-code-based (gate's
process note — already fixed + memorized). STANDS: UAT-2 has NO evidence in
the record — founder-executed (external design partner log set, docs/05 §5),
not remediable by the build, awaiting founder decision (run it or rule it
waived/deferred).

## PRE-LAUNCH CLOSEOUT + D11-12 vv GATE (FAIL → fixed; correction of record)

Branch `pre-launch-closeout`. Non-VPS items closed: FR-26 gap — idempotency
keys now purge with uploads (purge.py deletes keys for purged audits;
T-API-05 pin in test_lifecycle) ; MP-2 resolved — sample-report screenshot
on Home rendered from the SYNTHETIC waste_pack fixture (no customer data);
overdue vv-engineer D11-12 UAT-evidence gate RUN: FAIL with one real finding
— T-REP-03 schema test predated R-D6-AGG's Finding.detail key and had been
FAILING SINCE a8c3aa5. CORRECTION OF RECORD: suite-green claims from
R-D6-AGG merge through UAT-D5 (reported "193/197/199/206 passed") were
produced by a grep that matched the "N passed" substring INSIDE pytest's
"1 failed, N passed" line and masked the failure + exit code. Actual state
was 1 failed throughout. Test updated for the detail key (schema change is
the intended R-D6-AGG shape); suite now verified GREEN by exit code
(PYTEST-EXIT=0, 209 passed + 1 skip). Verification procedure fixed
(exit-code-preserving; lesson recorded in agent memory). Gate re-run below.
vv also flags: UAT-2 (external design partner, docs/05 §5) has NO evidence
in the record — founder-executed, still open, flagged to founder.

## LEDGER ROW 1 VERIFIED — LAUNCH THREAD UNBLOCKED (pending only D13 physical deploy)

Founder verification PASSED on the regenerated row (verbatim log line
appended to the golden-notes founder verification log): dedup independently
reproduced; spend independently re-priced within 2.5% conservative; model
mix + unpriced-exclusion confirmed. Ledger row 1 ticked "Lokesh Prasanna
Kumar S" — R-SELF-AUDIT rule 3 SATISFIED. Corrected UAT-1 figures APPROVED
for citation ($8,757.75/mo API-equiv, $2,846.62/mo est. waste, 32.5%,
67,095 unique calls of 159,571 events) — machine-side check printed to
founder: headline $2,846.62 == sum of 295 findings exactly (cap not
engaged, sum < spend), export file itself carries 0 duplicate ids,
row_count == unique_out 67,095. DEAD-FIGURE SWEEP: docs-site/CODE-TOUR/
PLAYBOOK/CHANGELOG/docs = zero references; PLAN R-SELF-AUDIT d annotated
SUPERSEDED (it had authorized the dead set); STATUS D11 history paragraph
annotated. Docs page still MEASUREMENT-PENDING for the trendline (1 of 3
verified rows). LAUNCH: unblocked pending only D13 physical deploy
(VPS/domain/SMTP — founder infra), then D14.

## UAT-D5 — LEDGER ROW 1 REFUSED, EXPORTER DOUBLE-COUNTING FIXED, ROW REGENERATED (resubmitted)

Founder-side verification REFUSED ledger row 1: exporter emitted one row per
transcript EVENT not per completed call (3,106 rows vs 1,304 unique
request_ids; one id ×10). Fix per ruling (branch uat-d5-exporter-dedup,
409a4f5): exporter dedupes globally by request_id (max-complete usage wins,
ties→latest; dedup summary printed every run); ingest warns loudly >1%
duplicate ids (ingest.duplicate_request_ids); D4 drops duplicate ids before
clustering (same id = same call). Regression: multi-event fixture (partial→
complete usage + cross-file replay) + shared-id-never-a-storm test + warning
tests. Goldens unaffected (NOTES row; estimators untouched); 206 passed.
LEDGER ROW 1 REPLACED (defective row deleted, never counts): re-run dedup
summary rows_in=3179 unique_out=1340 duplicates_dropped=1839 → $432.27
observed API-equiv, est. $1,966.27/mo waste, 30.3%, verified='' —
RESUBMITTED with dedup summary for founder tick. uat1 REGENERATED (session
overlap): 159,571→67,095 unique calls (58% duplicates), $8,757.75/mo spend,
$2,846.62/mo est. waste, 32.5% — waste share ROSE with the honest
denominator. Docs self-audit page defect log now carries UAT-D5 alongside
the 228% story ("our own verification gate refused our own first ledger
row"); corrected figures marked pending-verification. Launch thread remains
BLOCKED on a verified ledger row per R-SELF-AUDIT c.

## WP-SELF — BUILT (ledger seeded, page live behind publish gate; founder ticks pending)

Branch `wp-self`. scripts/self_audit.py (exporter on THIS project → CLI audit
→ ledger.csv row with verified='' + archived report; archives gitignored,
ledger committed). scripts/render_self_audit.py renders ONLY founder-verified
rows into docs-site/engineering/self-audit-data.md (MEASUREMENT-PENDING
below 3 rows; inline SVG trendline; CI --check drift gate). Page
engineering/self-audit.md carries the three mandatory verbatim rails, the
UAT-1 228%-defect story, and the intervention-experiment MP block. FIRST
LEDGER ROW: 2026-07-17 — 1 session, 3,106 calls, $916.36 API-equiv observed,
est. $3,674.99/mo waste (26.7%) — verified='' AWAITING FOUNDER TICK; nothing
publishes until ticked (test-enforced publish gate). Suite 199 passed + 1
skip; strict docs build green. Remaining before D14: founder ledger tick(s),
physical VPS deploy (founder infra), D14 launch go.

## D13 — GATE COMPLETE (ops-engineer PASS-WITH-NOTES; physical VPS deploy awaits founder infra)

ops-engineer D13 gate: PASS-WITH-NOTES — runbook §2 steps 3-7 all evidenced
(steps 1-2/DNS/SMTP correctly labeled VPS-only); concurrency evidence
honestly framed as dev-workstation numbers pending VPS re-validation; no
postgres ports, env-driven domain, non-root image, .env untracked; CHANGELOG
format conforms; NO blockers for the real deploy when credentials land.
Merged to main; tags d11+d12 (UAT milestones, sign-off recorded) and d13.

UAT-1 SIGN-OFF recorded (PLAN §0.1): sheet reviewed, both docs/05 §5 exit
criteria PASS. Branch `d13-deploy`. Runbook §2 executed end-to-end against
the REAL compose stack locally (caddy TLS → app → postgres + ofelia):
secrets-generated .env (600), build+up, alembic upgrade head in-container,
smoke ALL PASS — healthz db:true via Caddy, landing (control narrative +
early-access CTA served), magic link issue→verify→session cookie (log
adapter; SMTP unset), admin comp credit, F1 upload 201 → done → web report
200 → PDF valid. Ofelia: 3 jobs registered on correct schedules; backup.sh,
purge, digest all executed in-stack (digest showed 3 audits/3 payments/
signup line/pricing age/no alerts). CONCURRENCY MEMORY CHECK: 2× 195MB
(1.3M rows each) concurrent uploads → both done in 2m48s; peak app 4776MiB
+ postgres 93MiB ≈ 4.9GB vs 8GB budget — PASS with ~3.2GB headroom (the
D11 render-cap + D4 fixes are what made this bounded). CHANGELOG.md created
with the rehearsal entry (runbook §2 step 7). BLOCKED ON FOUNDER INFRA for
physical deploy: VPS hardware + domain/DNS + SMTP credentials; perf and
memory re-validation on VPS hardware happens at actual deploy. Stack torn
down post-rehearsal (ports freed); .env retained locally (gitignored).

## BATCH-2 RULINGS 2026-07-18 APPLIED — registers + landing copy (zero build-scope change)

Applied on main (255c6ae). R-GTM-CONTROL: landing leads with control
narrative, audit = step one of prevention path (only purchasable product);
early-access CTA verbatim "AI spend control — APIs, agents, and AI seats."
— POST /early-access email capture into append-only audit_log (no new table,
5/min limit), weekly count line in digest; T-WEB invariants (FR-23, one
primary CTA, attributed stats) test-verified; ux-reviewer re-checks changed
blocks at next scheduled gate. Registers: PLAN §0.1 gains R-GTM-CONTROL,
R-ENTERPRISE-SEAT, R-DEPLOYMENT-CONTRACT, R-ENTERPRISE-READY+R-MARKETPLACE
summary; BACKLOG.md rewritten — WP-P2-AGG three layers (day-45 PRD gate),
deployment contract (6 clauses), trigger register additions (Entra-first
SSO, Helm, marketplace+IaC, early-access counts), user-model principle,
explicit NOT-building list, enterprise sales notes. Batch-1 verified in
force, not re-applied. Suite 197 passed + 1 skip. Standing sequence
unchanged: sign-off → D13 → ops gate → WP-SELF → D14.

## D11 RULINGS 2026-07-18 APPLIED — R-D6-AGG + FR-30 built; uat1 artifacts regenerated (sign-off OPEN)

Branch `d11-agg-equiv`. Founder accepted all four UAT-1 fixes
(R-UAT1-FIXES-ACCEPTED). R-D6-AGG: D6 AND D4 now emit ONE finding per
session (shared split_on_gap in rules/base.py; gap = D6_SESSION_GAP_S) —
impact summed, run/cluster count in text, evidence sampled across
constituents, per-run/cluster breakdown in new Finding.detail → report.json
("detail" key; null for non-aggregated). Goldens UNCHANGED BY CONSTRUCTION
(fixture blocks are single sessions; derivation in NOTES sheet): D4 0.0510,
D6 0.096. FR-30 (R-EQUIV-SPEND): ReportModel.equiv_spend when any endpoint
== "claude-code"; verbatim line in header + methodology + JSON summary flag +
quickstart framing; T-REP-09. docs/01 FR-30 amendment + docs/04 row same
commit. WP-SELF (R-SELF-AUDIT) recorded in PLAN §0.1, scheduled post-D13.
Suite 193 passed + 1 skip; mypy/ruff/strict-docs clean. uat1/ artifacts
REGENERATED post-merge for founder review (per ruling item 5) — see report
below. D13 remains blocked on founder sign-off (R-SEQ-POST-SIGNOFF).

## D11 UAT-1 DOGFOOD FIXES — first real-data run found 4 defects, all fixed (sign-off still OPEN)

Branch `d11-uat-fixes` (commits 488b40c = the four fixes below; 39a2d31 +
8bed596 = effective-rate + savings cap; pinned per vv gate note).
Founder ran the harness on real Claude Code logs
(1.6GB transcripts → 59.6MB counts-only export, 158k rows / 13 sessions /
36 days / $24.2k observed). FIRST RUN: killed after 25+ min at 18.4GB RSS.
Defects found+fixed, each with regression pins: (1) D4 no-hash fingerprint
was prompt_tokens-only → agent sessions read as retry storms (3,744
findings/20k rows); now (prompt,completion) AND cache-active rows excluded
(session continuations, not blind retries). (2) Report rendering unbounded →
WeasyPrint laid out ~30k finding cards (the 18GB); render_cap=50 top-by-impact
in web/PDF with explicit "top N of M" note, JSON always complete. (3) THE BIG
ONE: D3/D6 priced prompt-token savings at FLAT INPUT RATE — on cache-heavy
agent traffic (~10× inflation) the report claimed $46,020/mo savings on
$20,172/mo spend (228%, negative optimized projection). New shared
effective_prompt_rate(): tokens priced AS BILLED (cache reads at cache_read
rate); uncached rows reduce to input rate exactly → D3/D6 goldens UNCHANGED
(0.50/0.096), spreadsheet blend in golden notes. (4) headline savings now
capped at monthly spend, disclosed in METHODOLOGY; docs-site D3/D6 formulas
updated to match code. FINAL DOGFOOD RUN [figures SUPERSEDED by UAT-D5 —
exporter double-counting; citable set is in the UAT-D5 paragraph above]:
13s end-to-end, $5,289/mo savings
(26.2% of $20,200/mo), 965 findings (109 D3 + 856 D6), top D3 $173/mo,
<synthetic> correctly unpriced, PDF 239KB. Suite 189 passed + 1 skip; mypy/
ruff/strict-docs clean. OPEN QUESTION for founder review: 856 D6 findings =
one per run — consider aggregating per session/tag (product call). UAT-1
sign-off remains FOUNDER-ONLY; review artifacts in uat1/ (gitignored).

## D11-12 PREP — perf PASS + authorized items done (UAT sign-off gate OPEN)

Branch `d11-12-prep`, merged to main WITHOUT milestone tag per
R-D11-12-PARTIAL (D11-12 completes only when founder dogfood report lands;
vv-engineer UAT-evidence gate then runs on the full since-d-docs range).
T-PERF-01 EXECUTED MANUALLY per R-PERF-MANUAL: 1M rows in 94.3s wall-clock
(bound 600s) — ingest 8.5s, price+reconcile 1.2s, detect 82.8s,
assemble+render 1.9s; peak RSS 1771MB; 17,264 findings from planted waste;
machine = Ryzen AI MAX+ 392 / 27GB / Ubuntu 24.04 (dev workstation — VPS
re-verification noted on the docs page and due at D13). MP-6 FILLED in
docs-site performance.md (spec stated; extrapolation avoided). F7 generator
scripts/gen_perf_fixture.py (seeded, priced-OpenAI-only after 10k smoke
caught openai/claude-* unpriced rows; fixture gitignored). Ingest
enhancement: JSONL parsers now honor precomputed top-level prefix_hash
(counts-only shipper contract, text wins when present) + tests. UAT-1
harness scripts/uat1_harness.py (export → CLI → review sheet CSV with
verdict/knob columns; smoke-tested on fixture sessions, D6 finding
produced). Runbook §8a knob table (env var / default / effect / when to
turn). Quickstart hardening: troubleshooting section + JSONL prefix_hash
guidance. Suite 179 passed + 1 skip + perf deselected by default; strict
docs build green. OPEN: UAT-1/UAT-2 sign-off is founder-only (docs/05 §5
exit criteria cannot be self-certified) — awaiting dogfood report.

## D-DOCS — GATES COMPLETE (ux PASS-WITH-NOTES, spec-guard PASS)

Gate verdicts. ux-reviewer (charter extended to docs-site per DOCS-PLAN §5.6):
PASS-WITH-NOTES — home value-prop/attribution/FR-23/nav/tabs/MP-blocks all
clean; single note (RAG/few-shot/corpus-median jargon unglossed on
prompt-bloat page) FIXED same-day. spec-guard: PASS — 10/10 claim spot check
verified against sources (FR-23 x2, three attributed stats vs docs/09b, five
golden dollar figures vs pricing_golden_NOTES.md), banned stats absent,
MP blocks number-free (test-enforced), mkdocs-material dev-only, DOC column
complete with existing targets, FR-22 hygiene clean. Merged to main; tag
d-docs.

Branch `d-docs`. MkDocs + Material (dev-only dep per DOCS-PLAN §1), 27 pages
per approved page tree, mkdocs.yml strict + local palette (no CDNs/fonts/
trackers), pymdownx snippets transclude docs/04 (traceability page) and
docs/uml/*.mmd (architecture page). scripts/export_openapi.py generates
api/endpoints.md from the app factory; --check drift gate + `mkdocs build
--strict` + artifact upload added as CI `docs` job. docs/04 gained the DOC
column (same commit as pages). MP register at build: RESOLVED with real repo
numbers — MP-3 (20 endpoints generated), MP-5 (G4 UML embedded), MP-7
(determinism via T-REP-03/08), MP-8+MP-10 (all six golden rows: D1 $1.35,
D2 $0.246784, D3 $0.50, D4 $0.0510, D5 $0.00 informational, D6 $0.096),
MP-9 (legal single-sourcing: web templates authoritative, docs mirror,
drift-failing sync tests in tests/test_docs_site.py — clause structure +
FR-23 + price). STILL PENDING (greppable MEASUREMENT-PENDING blocks):
MP-1 e2e timing claim, MP-2 report screenshot, MP-6 perf numbers (founder
precondition: ≥1 successful nightly perf run; none exists yet). Stats
policy test-enforced (attributed 79/31/98 only; 40-60/73 banned). Suite
177 passed + 1 CI skip; strict build zero warnings.

## D10 — G6 SWEEP COMPLETE (ops-engineer PASS-WITH-NOTES, vv PASS-WITH-NOTES)

G6 verdicts. ops-engineer: PASS-WITH-NOTES — container_name/ofelia targets match,
mounts correct, compose valid, no postgres ports, FR-29 status-file paths agree,
Dockerfile chown covers scripts/. Notes FIXED same-day: runbook §4 reworded
(tar snapshot, not rsync — postgres image ships none), digest disk check now
samples uploads AND backups filesystems (deduped). vv: PASS-WITH-NOTES —
171 passed + 1 CI skip reproduced; coverage 93.7%/100%/100% (aggregate gate);
T-LIF value-asserting incl. due-vs-not-due discrimination; T-OPS-04 byte-identical
never-write assertion confirmed; no money-math files touched. Notes: stale fixture
comment FIXED; purge.py main() CLI lines uncovered (78.4% file-level, acceptable —
CLI exercised by ops drills; revisit only if per-file gates tighten). Restore
drill evidence accepted (runbook §4 log). Merged to main; tag d10.

Branch `d10-lifecycle-ops`. R-TOOLCHAIN recorded first (TE-11 in docs/10 §2 +
CLAUDE.md verbatim copy + all six charters). lifecycle/purge.py (FR-21): due =
report_ready_at + PURGE_AFTER_DAYS, created_at fallback for failed/never-rendered
audits (decision: FR-23 "nothing retained beyond 7 days" must hold on failure
paths); removes upload dir only, keeps reports+aggregates; audit_log actor
system@purge {"mode":"scheduled"}; module CLI for ofelia. scripts/backup.sh
(NFR-08): runs INSIDE postgres container (ofelia job-exec), pg_dump -Fc
write-then-rename (no partials in freshness check), 14d rotation, reports
snapshot (rsync-or-tar fallback), env-gated rclone offsite. ofelia.ini jobs
wired: purge 02:00, backup 02:30, digest 03:00 UTC; compose pins
container_name for both job targets, new backups volume (rw postgres, ro app),
scripts+reports mounted ro into postgres; Dockerfile now COPYs scripts/.
scripts/daily_digest.py (runbook §3): audits/failures/revenue/purges 24h +
ALERTS (backup>26h or absent, disk>80%, pricing age NFR-15, refresh failures
FR-29, failed audits); DIGEST_TO+BACKUP_DIR added to config+.env.example;
SmtpMailAdapter.send_digest. scripts/pricing_refresh.py (FR-29): read-only —
parses # source_url comments, heuristic candidate extraction, diff output
(new ids / VERIFY-BY-HAND mismatches / unreachable); NEVER writes prices.yaml;
status JSON to <report_dir>/.ops/pricing_refresh.json consumed by digest.
Tests: T-LIF-01..03 (5), T-OPS-04 + digest (6); suite 171 passed + 1 CI skip;
mypy/ruff clean. RESTORE DRILL T-OPS-01/02 EXECUTED with real postgres:17
containers — logged in runbook §4 (88s, PASS, identical row counts, new smoke
audit on restored db). Traceability rows for FR-21/29, NFR-08/15 pre-existed.

## D8-D9 — G5 SWEEP COMPLETE (ux PASS-WITH-NOTES, cold FAIL→fixed→PASS-WITH-NOTES, spec-guard PASS-WITH-NOTES)

G5 verdicts. ux-reviewer: PASS-WITH-NOTES — notes fixed same-day (jargon glossed,
founder-approved differentiation line verbatim). cold-reviewer: FAIL with 5 findings,
all remediated in 488b40c with regression pins — (1) credit double-spend race →
claim_credit atomic UPDATE-where-unclaimed loop; (2) same-second magic-link lockout →
float-epoch iat; (3) webhook parse exceptions 500 → try/except → None/"ignored";
(4) admin actor honors X-Forwarded-For behind Caddy; (5) mark-paid rejects negative
amounts. Re-run initially re-FAILed claiming `except A, B, C:` is a SyntaxError —
WITHDRAWN as false positive: reviewer's ast.parse ran under pyenv 3.13; project pins
Python 3.14 everywhere (pyproject/.python-version/Dockerfile/CI) where PEP 758 makes
unparenthesized multi-except legal, and ruff format (py314) ENFORCES that style
(reverts parenthesization). Verified under uv 3.14.5: py_compile OK, mypy 65 files
clean, ruff clean. spec-guard: PASS-WITH-NOTES — FR-19 "download report" admin action
was missing; ADDED (GET /admin/audits/{id}/report, PDF, audit-logged, T-ADM-05,
traceability + test-plan updated, 1a7d882). Final: 160 passed + 1 CI-only skip.
Merged to main; tags d8, d9.

Branch `d8-d9-auth-payments`. D8: web/auth.py (magic tokens 15-min + sessions;
SINGLE-USE via users.last_login_at — any earlier link dies on login, no
consumed-token table), web/routes_auth.py (request/verify/logout; enumeration-
safe response; 5/min limit), session cookie HttpOnly/Secure/SameSite=Lax
(TTL Q11); api current_user now cookie-FIRST with X-User-Email as NON-PROD shim;
templates base/landing/upload + legal/{terms,privacy,dpa} (FR-23 verbatim on
landing+privacy+footer; ONE primary CTA; R-ICP agent-fleet headline; approved
79%/98% stats only; auto-router differentiation line); mail/smtp.py env-gated
(STARTTLS; APP_BASE_URL added to config for absolute links). NFR-11 BUG FOUND+
FIXED: naive sqlite datetimes interpreted as local time in epoch math — now
normalized to UTC by contract. D9: payments/{base,razorpay_link,stripe_link}
(stdlib HMAC only; FR-27 razorpay tolerance via payload created_at — documented,
signature carries no timestamp; stripe via t= param), api/routes_webhooks
(/api/v1/webhooks/*; order: signature→tolerance→append-only webhook_events
dedup→credit), FR-18 ENFORCED: one paid credit consumed per audit atomically,
402 + payment links otherwise (Q8 comp = provider comp/amount 0);
web/routes_admin (X-Admin-Token constant-time, 404 when unset, IP-logged actor,
list/rerun/purge/mark-paid, all audit-logged). Migration 002 additive (payments,
webhook_events, users.last_login_at). Architect G4 note DONE: repo-pattern
helpers (create_audit/get_user_audit) — routes no longer touch ORM directly.
Tests: T-AUTH-01..04, T-WEB-01, T-MAIL-01, T-PAY-01..07 (independent HMAC
fixtures per R-PAY), T-ADM-01..05; existing API tests updated for credit
enforcement. Suite green; coverage 94.4%/100%/100%.

## D6-D7 — G4 SWEEP COMPLETE (architect PASS-WITH-NOTES + UML, vv PASS, ux PASS-WITH-NOTES)

architect: placement per LLD §1 clean; layering verified (ReportModel sole money
assembly; renderers serialize only); ADR-1/2/3/4/5 conform; two disclosed
founder-authorized deviations accepted; docs/uml/{components,audit-seq}.mmd
EMITTED from the D6-D7 implementation (no D7-vs-D6 boundary change). Notes:
repo-pattern applied inconsistently in routes_upload (tighten at D8 refactor);
bar-width percentages are presentational only. vv: 127 passed + 1 designed skip,
coverage 94.5%/100%/100%, no money-math files touched, envelope/idempotency/
queue/signer tests all value-asserting; nit (pandas import placement) fixed.
ux: headline savings in first view, charts titled+labeled, page-breaks, fluid
layout all PASS; notes FIXED same-day: "normalized" label replaced with plain
"scaled to 30 days" wording, #N-by-impact rank badges added to waterfall and
finding cards. Merged to main; tags d6, d7. D-DOCS unblocked per R-SEQ-D6D7.

## D6-D7 — runner + reports complete

Branch `d6-d7-runner-report`. D6 file map: persistence/{models,repo}.py + alembic
migration 001 (six tables incl. idempotency_keys per FR-26; additive-only),
services/runner.py (queued→processing→done|failed, NFR-13 slot admission,
idempotent re-run, user-safe failures, audit_log events), services/report/
{model,render_json}.py (ReportModel assembled ONCE — render layers never
recompute; deterministic JSON; FR-28 pricing provenance; methodology carries
C3 floors + R-Q4/R-Q5 haircuts + R-D1-MAP caveat), lifecycle/auditlog.py
(INSERT-only), mail/base.py (port + log adapter), api/routes_upload.py
(/api/v1 per FR-25; streaming 200MB cap; Idempotency-Key 201/200 per FR-26;
queue position per NFR-13; pre-D8 auth stub X-User-Email non-prod only +
pre-D9 payment-gate stub, both behind dependencies), NFR-12 user-else-IP
limiter keying w/ Retry-After, NFR-14 envelope on all /api/* errors.
D7 file map: report/signer.py (30-day signed URLs), report/render_pdf.py
(weasyprint; render_report_html shared), web/templates/{_report_body,
_report_style,report,pdf/report}.html (single shared body — web and PDF cannot
diverge; headline savings number first; findings ranked; CSS bar charts with
titles/labels; evidence tables counts-only; page-break rules), web/
routes_report.py (GET /r/{token} + /r/{token}/pdf; NOT under /api/v1),
cli.py + console script `tokenops-cost-auditor` (FR-04; offline pipeline,
exit 0/2/3). Deps: python-multipart (approved). CI: weasyprint system libs in
test job. LLD §5 deviation note for architect: API paths carry /api/v1 prefix
per FR-25 founder amendment (docs/03 §5 predates R-API). Runner renders
JSON+HTML+PDF, mails signed /r/ link. Tests incl. T-API-01..07, T-NFR-03/12,
T-REP-01..08, T-LIF-04, T-NFR-11, T-CLI-01, postgres L2 (CI), determinism
repeat-render. Dogfood path for UAT-1 ready: exporter → CLI → PDF (no auth
needed) or API with stub header.

## D4-D5 — G3 SWEEP COMPLETE (vv PASS, spec-guard PASS, cold-reviewer PASS-WITH-NOTES)

vv-engineer: 86 tests green, all 15 in-scope T-RUL/T-NFR IDs non-trivial, money-math
discipline satisfied, coverage 94.1% / 100% / 100% — no notes. spec-guard: every
change maps to FR-07..13/NFR-01, X-02 observe-only confirmed (no enforcement
anywhere), FR-22 clean (EvidenceRef counts-only, fixed-vocabulary notes), fix_text
deterministic templates (X-04-consistent). cold-reviewer: 5 findings, ALL FIXED
same-day (commit ca5aed6): (1) D2 buckets spanning a pricing effective-date
boundary now reprice per row/day — regression test with independent expected
1.55136 across the Sonnet-5 Sep-1 boundary; (2) D4 mixed priced/unpriced clusters
count priced rows only (conservative); (3) D6 mixed-model runs priced at run-min
input rate (order-independent); (4) tz-naive timestamps assumed UTC defensively;
(5) '-2' suffix rule commented. Merged to main; tags d4, d5.

## D5 — rules part 2 (complete, all green)

Branch `d4-d5-detectors`. File map: services/rules/{d1_oversized_model,
d3_prompt_bloat,d5_unbounded_max_tokens,d6_chatty_loop}.py; registry now runs
D1..D6 in order; tests/test_import_guard.py (T-NFR-01, AST-based, self-testing);
waste_pack v2 (147 anthropic + 17 openai lines, 6 engineered blocks + filler).
Golden verdicts on waste_pack v2 — EXACTLY one finding per detector, all matching
independent Decimal derivations (NOTES waste_pack v2 section): D1 1.35 / D2
0.246784 (unchanged) / D3 0.50 / D4 0.0510 (unchanged) / D5 0.00 informational /
D6 0.096; clean_optimal = zero findings across all six. R-D1-MAP implemented
fully: config-seeded frontier map (dated comments), one-tier/same-provider,
re-price-at-suggested-card savings, QUALITY_CAVEAT verbatim in every D1 finding,
unmapped-frontier -> D1-INFO informational. NEW money-math defaults recorded in
NOTES (D3 excess definition, D6 overhead=run-median prompt, D1 repricing
equivalence). BEHAVIOR CHANGE flagged for gates: model-key matching in pricing
table + D1 map tightened to exact-or-dated-suffix boundary rule (prevents
gpt-5.4-nano taking gpt-5.4's card; G12 golden still exact). New config knobs:
D5_MAX_RATIO, D6_SMALL_COMPLETION_T/RUN_WINDOW_S/SESSION_GAP_S/REREAD_MIN,
D1 map seeds (.env.example updated, completeness test green). Boundary tests:
p50 149/150, bloat 2.0x edge, D5 4x edge + absent max, LOOP_MIN 7/8, session-gap
split, sibling-bleed guard, cached-bucket exclusion.

## D4 — rules part 1 (complete, all green; G3 fires at end of D5)

Branch `d4-d5-detectors`. File map: services/rules/{findings,base,registry,
d2_missing_cache,d4_retry_storm}.py; fixtures waste_pack_anthropic.jsonl +
waste_pack_openai.jsonl (split per-file format detection; tests concat) +
clean_optimal.jsonl; tests/test_rules.py (19 tests: T-RUL-00, T-RUL-EV-01,
T-RUL-D2-01..03, T-RUL-D4-01..02). Golden derivations in pricing_golden_NOTES.md
(waste_pack v1 section): D2 monthly 0.246784 (13 TTL windows/17 reads/cacheable
1024), D4 monthly 0.0510 — both independently Decimal-computed; the independent
calc CAUGHT a real bug (pandas 3.0 datetime64[us] broke nanosecond-based window
math; fixed with Timedelta division). Decisions: one Finding per D2 bucket / per
D4 identity group; D2 severity impact-scaled (high>=500,med>=50 — in NOTES), D4
severity per LLD cluster>=10 rule; hash-verified cacheable capped at
PREFIX_HASH_CHARS//4 tokens; R-Q4 0.7-haircut branch implemented + tested via
window-estimation failure injection; TTL per provider-family wired (C4 consumer
now exists — closes G2 re-run note 2/4). clean_optimal engineered to stay silent
through D5 detectors too. rules_disabled config added (T-RUL-00). D5 next: D1/D3/
D5/D6 detectors, waste_pack v2, T-NFR-01 import guard; then gate sweep G3.

## D2-D3 — G2 SWEEP COMPLETE (vv-engineer PASS-WITH-NOTES, cold-reviewer PASS-WITH-NOTES)

Founder verified golden CSV 2026-07-17 (log in pricing_golden_NOTES.md), then G2 ran.
vv: suite green, coverage 94.1%→94.5% services / 100% coster.py, golden discipline
satisfied; note was a stale STATUS header (fixed here). cold-reviewer: money math
verified against all 12 golden rows; 4 non-blocking findings, ALL FIXED in main
thread same-day with regression tests (TestG2ReviewFindings): (1) present-but-invalid
cached/cache_write_tokens now a row error, never silent 0; (2) anthropic parser
accepts integral-float usage counts, rejects garbage via prompt_tokens invalidation;
(3) generic CSV blank provider value = row error, not silent "generic" default;
(4) reconcile() docstring now states exactly what it does/doesn't validate.
Merged to main; tags d2, d3.

## D3 — pricing (complete; founder-verified)

Branch `d2-d3-ingest-pricing`. File map: services/pricing/{table.py,coster.py,
data/prices.yaml}, tests/test_pricing.py, tests/fixtures/pricing_golden.csv +
pricing_golden_NOTES.md. prices.yaml seeded from OFFICIAL pages fetched 2026-07-17
(Anthropic pricing page incl. exact cache write/read columns; OpenAI
developers.openai.com pricing) with effective_from + source_url per R-Q3; four rates
per R-Q4 (cache_write = 5-min-TTL rate; OpenAI cache_write defaults to input = zero
write premium). Sonnet-5 intro→standard boundary (2026-08-31/09-01) encoded and
boundary-tested. Coster: unified total-prompt semantics, negative-uncached clipped,
unknown model → NaN + unpriced list (audit continues). reconcile(frame, total)
verifies persisted headline total vs by-model/by-day parts ±0.5% (NFR-07); property
test (hypothesis, 200 examples). Golden values computed INDEPENDENTLY (Decimal
arithmetic, generator preserved in NOTES). Coverage: coster.py 100%, services 94.1%.
Fixtures regenerated with officially-priced OpenAI IDs (gpt-5.6-terra/5.4-mini/
5.4-nano — original invented IDs had no published rates). Money-math defaults
recorded in NOTES per R-Q6..12(a). D2_TTL_WINDOW_S=300 matches 5-min cache_write
choice. Per founder ruling: G2 (vv-engineer, cold-reviewer) runs ONLY AFTER founder
hand-verifies 8-10 golden rows.

## D2 — ingest (complete, all green)

Branch `d2-d3-ingest-pricing`. File map: services/ingest/{base,openai_jsonl,
anthropic_jsonl,generic_csv,normalizer,validator,__init__}.py;
scripts/exporters/claude_code_export.py (FR-24, R-ICP); fixtures F1-F4 + Claude Code
session fixture + seeded generator. Decisions: per-file format detection (mixed-
provider JSONL = format error, F3 is single-provider with mixed error KINDS);
CallRecordFrame gains cache_write_tokens column (R-Q4; documented LLD §2 deviation —
architect gate note for G4); unified prompt_tokens = TOTAL input semantics
(OpenAI includes cached; Anthropic input+read+write summed); prefix_hash in-memory
only, text keys stripped from raw_extra (FR-22); request_id synthesized r{line_no}
when absent. Exporter emits Anthropic-shaped JSONL, counts only, sessionId as tag,
endpoint "claude-code"; T-EXP-02 asserts no text survives. 28 tests (T-ING-01..09,
T-EXP-01..02) green.

## D1 — scaffold (COMPLETE; G1 verdicts: ops-engineer PASS, spec-guard PASS-WITH-NOTES)

G1 notes (non-blocking): re-diff .env.example vs config.py directly at D6; config.py
pre-declares FR-18/FR-20/detector settings ahead of owning milestones (intentional —
kickoff requires .env.example to cover every docs/03 §7 variable from D1).


Scaffold from scratch per PLAN.md WP-D1 on branch `d1-scaffold`. Python 3.14 (wheel +
install verification in PLAN.md §0.2). Founder ruling R-NAMING applied mid-milestone:
full product name everywhere — package is `src/tokenops_cost_auditor/` (not
`src/tokenops/`), distribution `tokenops-cost-auditor`, DB/user/container names
likewise; path strings in docs/01 (FR-04 CLI name), docs/03 §1 tree, docs/04 coverage
rule, and the ux-reviewer charter were updated to match — founder to re-confirm at D1
stop. File map: config.py, main.py (app factory, request-id middleware, /healthz with
db+disk checks), obs/{logging,errors,ratelimit}.py, persistence/{models,repo}.py +
alembic (no tables yet, additive-only), package skeleton per LLD §1, Dockerfile,
docker-compose.yml (caddy→app→postgres:17 + ofelia sidecar, postgres internal-only,
log rotation), Caddyfile, ofelia.ini (jobs commented until D10), .env.example
(complete vs config.py, test-enforced), .github/workflows/ci.yml (lint→type→test w/
postgres service→coverage gate→build; perf nightly-only; deploy manual),
scripts/coverage_gate.py, tests (T-OBS-01..03 + env-completeness; 6 passed; ruff,
mypy clean; compose config valid). Decisions: sentry-sdk NOT a dependency — NFR-06 hook
is env-gated lazy import; httpx added DEV-ONLY for TestClient (docs/05 L3). Open
questions for founder: (1) approve `pyyaml` dependency at D3 (FR-05 YAML table, no
stdlib parser) and `python-multipart` at D6 (FastAPI multipart upload); (2) confirm
doc-string updates made under R-NAMING; (3) R-Q1 nuance — UML emission lands at the
D6-D7 group gate (end of D7). Market-research refresh running; report to
docs/09b-MARKET-RESEARCH-REFRESH.md.


## V-D10 (2026-07-23) — harden + ship prep

Coverage debt CLOSED, not carried: smtp.py 83.8%->100%, purge.py 80.0%->97.5%
(residual = the `__main__` guard). Both were untested production paths:
purge.main() is the FR-21 deletion promise running under cron and nothing had
ever executed it — the same hole that hid the monthly-statements NameError,
but failing open here means retaining uploads we told customers were deleted.

DEPLOY REHEARSAL on a production-shaped copy (details in CHANGELOG). Ran as an
isolated compose project because the live local stack was already up with
populated volumes; the real stack was never recreated. Full migration chain
001->007 applied from empty on postgres:17, each revision reporting by name.
Full suite green against Postgres with ZERO skips — the postgres-gated test
that skips locally ran and passed, exercising with_for_update row locks that
are no-ops on SQLite. FR-22 re-verified against the DEPLOYED schema.

DISCREPANCY OF RECORD: the standing order said migration chain "001->006".
The chain runs to 007 (statement email preference, V-D7). Rehearsed to 007.

Three defects found and fixed:
1. Terms of Service (web + docs-site mirror) quoted $500 / ₹20,000 per audit
   while the price config charges ₹45,000 — a binding document 44% under
   what an Indian customer's card is charged. Root cause was the guard: the
   MP-9 test pinned the literal in BOTH mirrors, certifying they agreed with
   each other while both disagreed with checkout. Terms now renders from the
   one price config; the test derives its expectation from that config and is
   mutation-verified to fail on drift.
2. `alembic upgrade head` (runbook §2 step 5) printed NOTHING — env.py never
   applied alembic.ini's logging config, so the riskiest step of a production
   deploy gave an operator no way to distinguish 7 applied revisions from a
   silent no-op.
3. alembic path_separator deprecation pinned rather than left to a future
   default.

Deferrals per founder ruling: report web visual pass -> BACKLOG as its own
post-launch gated milestone (shared PDF template + golden pins). Pricing-page
Savings-Statement framing: NOT taken into V-D10 — the day was spent on the
pricing-truth defect and the rehearsal, which is not "genuine slack"; it goes
to BACKLOG beside item 1 unless the founder directs otherwise.

Open for founder: launch asset post 8/ now leads with Free->Pro subscription
and demotes the $500 one-off to an enterprise line. That is a positioning
change, not a figure correction — flagged in the asset approval checklist.
Terms §4/§6 still describe a per-audit business only; they do not mention
subscriptions at all, and §6 caps liability at "the amount you paid for the
audit in question", which is undefined for a subscriber. I did not author
contract language for that — founder/legal call.

### V-D10 gate round (2026-07-23) — three gates, all PASS-WITH-NOTES

ops-engineer, spec-guard FINAL SWEEP and vv full all returned
PASS-WITH-NOTES on the settled diff. Notes actioned:

- ops f.1 (REAL, and my fix for it was itself wrong twice): the pass-1 fix
  used logging.config.fileConfig, the stock alembic template, which rebuilds
  every logger named in the ini INCLUDING root — and alembic is driven
  in-process here (tests/test_runner.py:233 calls command.upgrade in the same
  interpreter as pytest), so it would tear the JSON handler off root
  mid-session. Replaced with configuration of the `alembic` logger alone.
  That replacement then silently did nothing, because it guarded on
  `if log.handlers` and the alembic package ships a NullHandler on its own
  logger — so the guard was always true and skipped the whole function. Now
  tests for a NON-Null handler and raises the level either way. Caught only
  because the second rehearsal pass re-ran the real command and saw silence
  again; the code looked correct both times.
- ops f.4b (REAL GAP): pass 1 migrated only from empty. Second pass rehearsed
  the incremental path over live data — see CHANGELOG. Result: additive
  migration verified safe, NULL statement_emails correctly reads as opted-in.
- ops f.4a / f.4c: recorded as known gaps rather than papered over.
- ops f.5: CHANGELOG entry now carries the rehearsed SHA.
- vv f.1: purge.main() now disposes its engine — as a cron one-shot process
  exit covered it, but main() is callable in-process (and now is, from the
  test) where each call leaked a live connection.
- vv f.8: test class renamed TestFR21PurgeCliEntrypoint, following the
  TestFR26... precedent rather than inventing a T-LIF id docs/05 lacks.
- spec-guard f.1 (it could not verify under its charter; I did): the asset
  claim "no prompt text in that API, so there is none in our database" is
  TRUE — openai_usage.py:46-47 and anthropic_usage.py:57-58 map provider
  usage-report fields to counts only.
- spec-guard f.6 / vv f.7 confirm no traceability row is owed: nothing here
  implements a new FR, and the Terms price change is a copy correction, not
  an estimator change, so CLAUDE.md rule 4 does not apply.


## R-LANDING-2 — UNBLOCKED AND GO (founder, 2026-07-25; block record kept below)

All four questions answered: order self-contained + satisfied by wiring; 98%
figure replaces the dropped unsourced card; the §5 header line RELEASED;
dress-in-place confirmed. Budgets are the gate evidence (Lighthouse only if
installable). R-STMT-GATING recorded in PLAN §0.1 and implemented. Carried
debt accepted.

## R-LANDING-2 received 2026-07-24 — original block record (R-PREMISE-CHECK)

The ruling's stated prerequisite does not exist in the record: there is no
incident/funnel order, and therefore no Part B skeleton for this to dress.
Paused per the law recorded the same day. Four further items need a founder
answer before this can start cleanly:

1. MISSING ORDER. Send the incident/funnel order, or confirm R-LANDING-2 is
   self-contained and should build its own skeleton.
2. FIGURE INVENTORY GAP. Section 2 calls for three attributed stat cards
   including a "#1 unmet ask" figure. The approved inventory carries 79%
   (DoiT/Sapio 2026), 31% mature-teams (same survey) and 98% (State of FinOps
   2026). There is no attributed "#1 unmet ask" stat on file. Under the
   no-invented-numbers law extended by this very ruling, it cannot be written
   until a source exists.
3. REGISTERED LINE NOT RELEASED. Section 5's header "We run the architecture
   we audit you toward" sits in launch-assets-DRAFT under "Registered lines
   (not yet approved for use)" per R-ARCH-PATTERNS. Using it on the landing
   needs an explicit release.
4. SUPERSESSION. The v4 landing mockup (branch v15-ui-unify, ux-gated
   PASS-WITH-NOTES, awaiting founder review) is a 1-section-hero + 6-section
   page. R-LANDING-2 specifies a 9-section page that absorbs and replaces it.
   Confirm v4 landing is superseded so the founder review of v4 covers only
   sources/upload/legal, or that v4 landing ships first as an interim.

TOOLING NOTE: Lighthouse >= 90 mobile is specified as a GATE criterion. No
Lighthouse is installed in this environment; a headless Chromium exists in the
playwright cache but the CLI does not. Gating on evidence that cannot currently
be produced would make the gate unfalsifiable, so this needs either an install
or a substitute measurable criterion.

---

O-1b-1 (workspace switcher) — 2026-07-24, founder "proceed as recommended". The
workspace spine gains its UI: the topbar shows the active workspace on EVERY app
page ("acting in <name>"), and a user in more than one workspace switches between
them in one click (details/summary, reuses the ux-approved account-menu pattern;
a solo user gets an honest plain indicator, NO dead control — respects the shell's
no-coming-soon rule). The reachability law is held by ONE helper,
web/shell.py::workspace_bar, called by both the _shell_ctx pages AND the
manual-render ones (sources, connect_wizard, developer, upload) — so the indicator
can never be present on some pages and missing on others. POST
/settings/workspace/switch → repo.set_active_workspace (membership-validated; a
forged/foreign workspace_id is a silent no-op; audit-logged; lands on /dashboard so
the flip is visible). Switching flips every owned read through the existing
active_workspace_id chokepoint — no per-read change — proven by
tests/test_workspace_spine.py::TestWorkspaceSwitcherJourney (shell shows active +
switcher; A→B flips the dashboard incl. its zero-state and freshness; non-member
switch refused and changes nothing; solo honest indicator; indicator reachable on
every app page incl. the manual-render ones). Mockup:
docs/design/mockups/workspace-switcher.html. File-map delta: +web/shell.py; +POST
/settings/workspace/switch; _shell_ctx and the 4 manual-render pages now call
workspace_bar. DEPENDS-DONE: O-1b backend. Next: O-1b-2 (invite & accept) uses this
switcher spine to drop an invitee into the shared workspace on accept.

---

O-1b-2 (invite & accept) — 2026-07-24, founder "proceed as recommended". The
workspace grows: an OWNER on the Scale plan invites a teammate by email from the
new Members surface (/settings/members — in the sidebar Account group + linked from
Settings); the invitee signs in with that address and is dropped INTO the shared
workspace, seeing its audits (auto-switch via O-1b-1's spine). Security grammar
mirrors the device link-code: the invite code is a SECRET shown once, emailed and
stored ONLY as a keyed HMAC (code_hash); acceptance requires the logged-in user's
email to MATCH the invite (a leaked code alone can't join a different account), is
single-use via an atomic UPDATE-where-unconsumed (rowcount-checked), and honors
expiry. Minting is OWNER-ONLY + Scale-gated (the plan sold as multi-seat) +
rate-limited (5/min). Honest states throughout: the invite form shows only for an
owner-on-Scale (others get the reason, no dead control); the accept page renders
ready/sign_in/wrong_email/invalid — never a raw 401 for an unauthenticated invitee.
New: web/routes_members.py, templates app/members.html + invite_accept.html,
mail.workspace_invite (base+log+smtp), repo.workspace_role + list_workspace_invites,
Members nav + help_registry entry. Proven by tests/test_workspace_invites.py
(owner→invite→accept→shared dashboard→third-party isolation; wrong-email/reused/
expired refused; owner-only + Scale-gated; honest states) + /settings/members added
to the O-1b-1 reachability walk. Mockup: docs/design/mockups/workspace-invite.html.
Engine untouched. DEPENDS-DONE: O-1b-1. Next: O-1b-3 (members roster + revoke).

---

LE-4 (gate round in CI) — 2026-07-25, founder "Build the loop enforcement
(LE-4/3/5)". THE KEYSTONE of loop engineering: the 5-7 adversarial gate agents
that were run BY HAND in the main thread now run HEADLESS in CI on the PR diff,
each emits its TE-8 verdict, and the check FAILS if any returns FAIL — turning
"gated by discipline" into "gated by machine". Mechanism: scripts/gate_round.py
computes BASE...HEAD, selects the gate set for the diff (core cold-reviewer/
spec-guard/vv-engineer/system-tester always; +ux-reviewer on customer surfaces;
+architect on services/models; +ops-engineer on workflows/infra — docs/09-SDLC
§4), invokes each agent's charter (.claude/agents/<name>.md) via the pinned
`claude -p` CLI, parses the TE-8 verdict (PASS|PASS-WITH-NOTES|FAIL, longest-
label-first so PASS-WITH-NOTES is never shadowed; a missing verdict = NO-VERDICT
= blocks), aggregates, exits non-zero on any FAIL/NO-VERDICT, and posts the
verdict table as a PR comment. .github/workflows/gate-round.yml runs it on every
PR. ACCEPTANCE CRITERIA (all met): (1) verdict parser handles PASS/notes/FAIL/
parenthesised/bolded/case forms + no-verdict; (2) gate selection matches
docs/09-SDLC §4 per-card schedule; (3) FAIL and NO-VERDICT block, PASS-WITH-NOTES
does not; (4) harness runs in CI with NO API key via --dry-run (always green,
proves selection/parse/aggregate/exit) and posts a PR comment; (5) unit tests
(32 at last count), lint+format clean, pinned toolchain. HONEST SCOPE (docs/09-SDLC §6): this ships
the MECHANISM, testable. The LIVE agent round is HELD on the founder adding the
ANTHROPIC_API_KEY repo secret + one validation run on a throwaway PR to confirm
the `claude -p` contract before the check is made required; until then only the
dry-run runs. New: scripts/gate_round.py, .github/workflows/gate-round.yml,
tests/test_gate_round.py. Engine untouched. DEPENDS: docs/09-SDLC (PR #24, held)
for the §4/§6 references. Next cards: LE-3 (auto-merge on all-green) then LE-5
(Issue-driven intake with acceptance criteria). WIP=1 — LE-3/LE-5 are separate
slices, not folded in here.

LE-4 VALIDATED LIVE — 2026-07-25, founder "added [secret], verify and validate".
Secret CLAUDE_CODE_OAUTH_TOKEN added; the live gate round ran headless in CI on the
founder's SUBSCRIPTION (Sonnet, TE-5) across 3 green runs on PR #25. Proven end-to-end:
credential detected → HAS_KEY flips → claude CLI installs → 5 gates auto-selected
(core + ops, diff touches .github/workflows) → each returns a parseable TE-8 verdict →
no FAIL → check green → verdict table + findings posted as a PR comment. The static
review caught a REAL parser bug (parse_verdict took the FIRST VERDICT match; a verbose
agent echoes the instruction's own example earlier, so a real FAIL could read as PASS)
— fixed to last-match. Also fixed from gate findings: subprocess wrapped so timeout/
missing-CLI → NO-VERDICT (fails CLOSED, ops-verified); --allowedTools Read,Grep,Glob,Bash
so agents EXECUTE the pinned toolchain (vv ran `uv run pytest` → 29 passed, TE-11 met,
not just static review); diff-truncation marker; OPS_TRIGGER tightened off bare
docker/compose substrings; dead `if: != schedule` dropped. Remaining PASS-WITH-NOTES are
non-defects: docs/09-SDLC refs resolve when PR #24 lands; full-repo coverage is out of a
single gate's 15-call budget (ci.yml owns it). OPEN FOLLOW-UP (founder): add the
gate-round check to branch protection to make it REQUIRED (docs/06-OPS-RUNBOOK §branch-
protection) — until then it reports but does not enforce merge-block. Next cards: LE-3
(auto-merge on all-green), LE-5 (Issue-driven intake). WIP=1.

## O-2 RBAC — roles over product actions (2026-07-25) — founder "merge and start LE-3" → chose O-2 (per ROADMAP §3 #1, the plan's next card, after I surfaced LE-3 is parked behind branch protection)

On branch `o2-rbac` off main (all of #23/#24/#25 merged first). The frontier card:
owner|admin|member|viewer over PRODUCT actions, enforced at the ROUTE boundary; the
audit engine (services/rules, services/pricing) stays ROLE-BLIND (R-ORG; T-NFR-01
import-guard unchanged). ROLE MATRIX (mockup docs/design/mockups/o2-rbac.html): view
reports/dashboard/runs = ALL; upload/run audits = all but viewer; manage sources +
mint/revoke keys = owner+admin; manage members (invite/revoke/set-role) = owner+admin
(admin over NON-owners only); billing/plan + delete-workspace/transfer-ownership =
owner only. viewer=pure read, member=operator, admin=governance-minus-money/ownership,
owner=all. ACCEPTANCE CRITERIA (SDLC §2 entry gate): (1) ONE require_role/permission
check at the route boundary gates every mutation, replacing today's ad-hoc inline
`workspace_role(...)=="owner"` checks (routes_members ×5); (2) each role's RENDERED
surface is pinned — a viewer/member never SEES a control it can't use (not merely a
403); (3) fail-closed — a forbidden mutation POSTed directly returns a clean honest
403/redirect, never executes; (4) owner assigns a role on INVITE (extends O-1b-2's form:
member|admin|viewer) and can CHANGE a member's role on the roster; admin may too, over
non-owners; (5) billing visibility becomes owner-only (resolves models.py:266 note);
(6) single-tenant unchanged — a solo user is owner of their workspace-of-one; (7) journey
test seeds ONE workspace with all four roles (membership rows) → walks each role's surface,
asserts each sees exactly its controls and each forbidden mutation fails closed; (8) mockup
before wiring + ux gate + full gate round. TWO CELLS held for founder lock: member can
upload/run (proposed YES), admin can manage members (proposed YES, not over owner).
STATUS: WIRED (founder "approved proceed next" 2026-07-26, matrix locked as proposed —
member runs audits, admin manages members). SHIPPED: web/authz.py matrix + repo.active_role;
route-boundary enforcement (routes_members invite+role/revoke/resend/cancel + NEW set-role;
routes_sources connect/validate/revoke; routes_ingest sdk mint/revoke; routes_devices
link/revoke; api create_audit RUN_AUDITS); rendered-surface gating (perms in _shell_ctx +
sources_page/billing) — members.html role select on invite + per-member role dropdown +
remove; sources.html connect/revoke/mint hidden for non-managers with honest notes;
billing.html owner-only. Proven: tests/test_authz.py (14, matrix cells) + tests/test_rbac_journey.py
(7, four-role surface + fail-closed mutations + viewer-can't-run). Engine role-blind (T-NFR-01).
Fixed in-slice: sources_page used scalar_one_or_none → a brand-new authenticated owner saw no
connect controls; now get_or_create_user so perms resolve. Held as a PR for founder merge; ux
gate + gate round run in CI. DEPENDS-DONE: O-1 (members/invites/revoke), workspace_role()
helper, Membership.role column.

## R-REACHABILITY #2 — in-app "View report" (2026-07-26) — founder "approved and proceed" (ROADMAP §3 #2)

Closes a real R-REACHABILITY gap: a completed report was reachable ONLY via the emailed
signed link (/r/{token}) — a customer who closed the email had no in-app way back to
their own report. NEW GET /audits/{id}/report (web/routes_runs.view_report): authenticated,
verifies the audit is in the caller's ACTIVE workspace + status=done (VIEW is universal —
every role incl. viewer may read; foreign/guessed id or not-done → 404, no cross-tenant
leak), mints a FRESH sign_report_url token, 303-redirects to the existing /r/{token} page
— ONE report-rendering path, reached in-app in one click. The Runs ledger (_runs_ledger.html)
gains a "View report" link per done run (report_ready flag). Proven: tests/test_view_report_
reachability.py (ledger links the report; click-through 303→/r/{token}→200 renders; stranger/
not-done/unknown → 404). endpoints.md regenerated (MP-3). Engine untouched. Held as a PR.
Next: ROADMAP §3 #3 (report plain-English parity) then #4/#7.

## LE-4 FOLLOW-UP — gate agents diff-scope their test run (2026-07-26) — founder "approved and proceed" (after O-2's vv NO-VERDICT)

O-2 (PR #26) exposed a real gate-machine hole: vv-engineer hit NO-VERDICT by exceeding
the 900s per-agent budget RUNNING THE FULL SUITE — a harness timeout on a large PR, not
a code defect, but it BLOCKS the (advisory) gate-round check and undermines trust in the
machine. ROOT-CAUSE FIX (scripts/gate_round.py): the agent prompt now states the full
suite + lint + type ALREADY run as REQUIRED CI checks that gate the merge independently,
so an agent must NOT re-run the whole suite — validate the DIFF (run ONLY the changed/
added test files if useful) and reason about the rest within the TE-6 budget. Belt-and-
suspenders: AGENT_TIMEOUT_S 900→1200s (constant, used in the message too) + gate-round.yml
job backstop 120→150min so the invariant "a hung agent hits its own ceiling first" stays
true at 7 gates. Pinned by tests/test_gate_round.py::test_prompt_tells_agents_not_to_rerun
_the_full_suite (+ timeout constant). Activated live on the next PR that carries the key.
Held as a PR for founder merge. Next: resume ROADMAP §3 queue (#2 view-report reachability).

## §3 #3 — report plain-English parity (2026-07-26) — founder "merge and continue once green" (ROADMAP §3 #3)

Closes the parity gap: /findings showed each detector's plain-English plain+summary (from
web/help_registry.yaml), but the downloadable report (web + PDF) couldn't — that copy lived
in the WEB layer and services/report can't reach up into web, so the report read more
technical than the in-app findings. FIX (as the ROADMAP specified — move the copy to a
services source): NEW services/rules/detector_copy.py is the SINGLE SOURCE of detector display
copy (all 9 detectors' plain/summary/why/fix/verify), moved VERBATIM from the yaml; the engine
stays network/LLM-free (T-NFR-01 — pure yaml→dict). web/help.py reads it (in-app copy
byte-identical, new home); help_registry.yaml drops its detectors section (no dual source).
render_pdf.render_report_html passes dcopy into the render; _report_body.html (shared by web
report.html + pdf/report.html) renders each finding's plain headline + summary — the SAME words
/findings shows. Proven: tests/test_report_web.py::TestReportPlainEnglishParity (one source
serves both consumers; the report renders each finding's plain+summary). mypy + import-guard +
all copy consumers (dashboard/explorer/journeys/first-run/wave4) + docs gates green. Held as a
PR. Next: ROADMAP §3 #4 (landing "Works with" rider) then #7 (O-4 workspace settings).

## O-4 WORKSPACE SETTINGS HOME (2026-07-26) — founder chose it (AskUserQuestion, after §3 #4 found already-done)

ROADMAP §3 #7, unblocked now O-2 landed. An ORGANIZING surface (no new capability): gather
the four scattered Account destinations into ONE tabbed settings home — General (today's
/settings: workspace name, peer-benchmark consent, data/purge), Members (/settings/members,
O-1/O-2 roster+invite+roles, RBAC unchanged), Sign-in (the auth methods — email magic link +
Google/Microsoft/GitHub federations, with enterprise SSO as the future row), Audit log (the
existing AuditLogEntry governance trail — who did what, counts/metadata only). The sidebar
"Account" group collapses to a single "Settings"; Members stops being a separate nav item.
ACCEPTANCE CRITERIA (SDLC §2 entry gate): (1) /settings is a tabbed home; each tab reachable
by click; deep links (/settings/members etc.) still resolve and select the right tab; (2) NO
capability change — same forms/actions, same RBAC (O-2 governs Members exactly as today; a
member/viewer sees the roster read-only, Audit log is workspace-scoped); (3) Audit log surfaces
real AuditLogEntry rows for the active workspace (FR-22 counts/metadata only, no prompt text);
(4) Sign-in shows the caller's methods honestly (no dead SSO control — stated as future);
(5) reachable end-to-end + the sidebar consolidation; (6) journey test walks every tab + the
RBAC gating; (7) mockup-before-wiring + ux gate + gate round. MOCKUP: docs/design/mockups/
o4-settings-home.html (interactive tabs, R-DESIGN-ADDENDUM documented). STATUS: WIRED (founder
"settings home good, wire it, fold Developer in" 2026-07-26). SHIPPED: _settings_nav.html tab
spine (5 tabs, server-rendered/deep-linkable, aria-current active) + wa-design.css .settings-tabs
(design source synced, CSS-parity law); the tab include on settings.html/members.html/developer.html
+ NEW settings_signin.html (email + enabled_federations, no dead SSO) + settings_audit_log.html
(repo.list_workspace_audit_log — AuditLogEntry scoped to workspace-member actors, FR-22 counts-only,
honest empty state); NEW GET /settings/sign-in + /settings/audit-log; sidebar "Account" group
collapsed to Settings + Billing (Members/Developer folded into tabs; Settings stays lit across all).
Each route passes settings_tab. RBAC unchanged (O-2 governs Members within the tab). Proven:
tests/test_settings_home.py (every tab renders + carries the full spine; each marks its own tab
active; sidebar collapsed; sign-in shows account + future-SSO; audit log surfaces workspace actions
+ honest empty state) + updated test_developer_platform reachability (sidebar→Settings→Developer
tab). mypy + import-guard + CSS-parity + docs gates green; endpoints.md regenerated. DEPENDS-DONE:
O-2 (RBAC), O-1b (members), existing /settings + auditlog + federations. Engine untouched. Held as a PR.
Next: ROADMAP §3 #9 (coverage debt) or #5 (landing rebuild).

## §3 #9 — coverage debt closed (2026-07-26) — founder "merge and continue with coverage debt"

The ROADMAP's numbers (smtp 83.8% · purge 78.9% · schedule 84.8%) were STALE — intervening
work had already lifted all three to ~95% (measured), above the 85% gate. Closed the last
edge/error gaps to 100%: (a) smtp.py:56 — SmtpMailAdapter.workspace_invite (the invite mail's
workspace subject + absolute accept link), test in test_auth.py::TestTMAIL01Smtp; (b) purge.py:57
— purge_one no-ops (returns False, stamps nothing) when there's no stored upload, test in
test_lifecycle.py (the admin route reaches it un-pre-filtered, V-D7); (c) schedule.py:107-109 —
the NESTED best-effort handler where recording a pull failure ITSELF fails, tick still counts the
error and never crashes, test in test_scheduler.py::TestTick. purge.py:100 (the __main__ script
guard) excluded with `# pragma: no cover` — an ofelia entrypoint, untestable via import. Result:
smtp/purge/schedule all 100%. No source behavior change (tests + one pragma). Held as a PR.
Next: ROADMAP §3 #5 (landing rebuild) or #8 (design batch).

## LE-3 — auto-merge on all-green (2026-07-26) — founder "Finish the loop (LE-3 + require gate-round)"

Completes the loop-engineering track's merge automation. .github/workflows/auto-merge.yml:
on a PR labelled `auto-merge` (and non-draft), arms GitHub's NATIVE auto-merge (gh pr merge
--auto --squash --delete-branch) — so the PR merges AUTOMATICALLY the moment every required
check is green, no human click. Branch protection is the real gate (nothing merges unless
authorship/lint/type/test/docs — and, once added, gate-round — pass); the workflow only
QUEUES the merge. Label-gated = opt-in per PR (the safe MVP until LE-6's kill-switch allows
default-on); removing the label or `gh pr merge --disable-auto` cancels it. Least-privilege
(contents+pull-requests write). Proven: tests/test_auto_merge_workflow.py (label-gated +
non-draft guard; native --auto so branch protection gates; triggers on labeled; least-priv
perms). TWO FOUNDER-LANE ACTIVATIONS (both authorised by the direction choice, applied by the
agent via gh api): (1) enable repo "Allow auto-merge"; (2) add gate-round to the required
checks so a gate FAIL/NO-VERDICT actually BLOCKS merge (was advisory). docs/09-SDLC LE table
updated (LE-3 shipped; LE-4 corrected to shipped-validated). LE-5 (issue driver) + LE-6
(kill-switch/observability) remain the loop's last rungs. Held as a PR.

## LE-3 ACTIVATED + gate-round now REQUIRED (2026-07-26)

Applied via gh api (founder authorised "LE-3 + require gate-round"): repo allow_auto_merge=true;
branch-protection required checks now [authorship, lint, type, test, docs, GATE-ROUND] — a gate
FAIL/NO-VERDICT BLOCKS merge (was advisory). enforce_admins stays false = the founder keeps an
override valve if a gate ever wedges. THIS PR is the LE-3 live demo: labelled `auto-merge`, it
squash-merges itself the moment all six checks (incl. the ~13-min live gate round) go green — no
human click. Loop status now: LE-1 authorship ✓, LE-3 auto-merge ✓, LE-4 gate-round ✓ (required),
LE-2 deploy HELD (founder DEPLOY_* secrets), LE-5 issue-driver + LE-6 kill-switch NOT BUILT.

## LE-6 — kill-switch + loop observability (2026-07-26) — founder "approved proceed next" (safety before LE-5's autonomy)

Built LE-6 BEFORE LE-5: a kill-switch for the automation just turned on is the responsible
order (safety before more autonomy). KILL-SWITCH: the LOOP_PAUSED repo variable, honored in
auto-merge.yml's job guard (`vars.LOOP_PAUSED != 'true'`) — `gh variable set LOOP_PAUSED --body
true` halts ALL auto-merge instantly; a human can always stop the loop. OBSERVABILITY:
scripts/loop_status.py — one screen showing paused?/auto-merge?/gate-round-required?/PRs armed/
gate-round pass rate (pure render_status + gh-backed gather_state); live output verified against
the real repo. Also fixed the LE-3 gotcha: auto-merge.yml now triggers on `opened` too, so a PR
created WITH the label arms immediately (no re-apply). Proven: tests/test_loop_status.py (render
signals) + tests/test_auto_merge_workflow.py (kill-switch in guard + opened trigger). This PR is
labelled `auto-merge` — it self-merges through the loop it hardens (dogfood). Loop now: LE-1/3/4/6
live; LE-2 deploy HELD (founder secrets); LE-5 autonomous issue-driver is the last, most
governance-heavy rung (fully-autonomous issue→merge) — deserves deliberate design + founder
alignment on the autonomy level before building.

## LE-5 — autonomous issue driver (2026-07-26) — founder "fully hands-off LE-5, any loop:ready issue"

The loop's capstone: label a GitHub Issue `loop:ready` → with NO human step the change is
implemented, PR'd, gated, and merged. scripts/loop_driver.py: select_ready (FIFO, skips
loop:in-progress) + build_prompt (the autonomous agent's instruction — encodes EVERY CI law
so the agent builds to the same bar a human slice does: CLAUDE.md/SDLC, scope-freeze
X-01..X-05, FR-22, T-NFR-01 engine boundary, R-VERTICAL slice, pinned toolchain green,
AUTHORSHIP LAW = Lokesh only + NO AI trailer, open PR with "Closes #N" + label `auto-merge`,
never self-merge/--admin, out-of-scope→BACKLOG) + run_agent (claude CLI, Read+Edit+Write+Bash,
3600s). .github/workflows/loop-driver.yml: on issues[labeled]=loop:ready + hourly sweep +
dispatch; LOOP_PAUSED kill-switch honored; concurrency=1 (never two agents at once);
checks out + auths with LOOP_PAT so the agent's PR TRIGGERS the loop (a GITHUB_TOKEN PR does
NOT fire downstream workflows — GitHub's recursion guard). .github/ISSUE_TEMPLATE/loop-task.yml
(goal + acceptance criteria + scope). Labels loop:ready + loop:in-progress created. Proven:
tests/test_loop_driver.py (select FIFO/skip-in-progress; build_prompt carries the issue + EVERY
law incl. authorship/scope/vertical/toolchain/Closes/auto-merge/no-self-merge; dry-run).
ACTIVATION (founder-lane): create a LOOP_PAT secret (fine-grained PAT: contents+PR+issues
write) — REQUIRED so the agent's PR triggers CI/gate-round/auto-merge; OAuth token already set.
FIRST RUN should be a TRIVIAL issue to watch the full autonomous cycle before trusting real
work. This PR labelled `auto-merge` (dogfood). Loop now COMPLETE: LE-1/3/4/5/6 built; LE-2
deploy HELD on founder DEPLOY_* secrets.

## Issue #37 — CONTRIBUTING documents the autonomous loop (2026-07-26) — LE-5's first live loop:ready run

The trivial first run LE-5's STATUS entry called for: Issue #37 asked for a docs-only
vertical slice, built here fully autonomously via loop-driver. Added a "The autonomous
loop" section to CONTRIBUTING.md: the loop-task template → `loop:ready` label → gate round
→ auto-merge flow; production stays founder-gated; the `LOOP_PAUSED` kill-switch
(`gh variable set LOOP_PAUSED --body true/false`); the `uv run python scripts/loop_status.py`
status command; and the discipline a `loop:ready` issue must meet (vertical slice, explicit
acceptance criteria, the CI laws the gate enforces — authorship, X-01..X-05, FR-22,
T-NFR-01, pinned toolchain). Proven: tests/test_contributing_docs.py asserts the section
exists and names `loop:ready`, `LOOP_PAUSED`, and `loop_status.py` so the doc can't
silently drift from the mechanism it describes. No loop workflows or scripts touched
(out of scope per the issue).

## Issue #38 — reconcile deploy-governance docs to founder-gated prod (2026-07-26) — LE-5 loop:ready run

Several docs still described the pre-2026-07-25 auto-deploy-to-prod design after the founder
reversed it (`docs/09-SDLC.md` §5: staging auto-deploys on merge, prod ships only on a
founder-triggered manual `workflow_dispatch` after reviewing rendered staging pages). Fixed
the drift, docs-only: `docs/internal/PLAN-LOOP-ENGINEERING.md`'s header, §0, the loop diagram's
DEPLOY step, the LE-2 slice bullet, and §3's risk framing now all state staging-auto/
prod-founder-gated and cite `docs/09-SDLC.md` §5 as authority; `docs/06-OPS-RUNBOOK.md` §10
step 5 (DEPLOY) matches; `docs/DEVELOPMENT.md`'s ship-diagram (§6) now shows the staging→
founder-review→manual-dispatch→PRODUCTION path instead of an unqualified auto-promote. No
workflow/code changes — `deploy.yml` already implements the founder-gated flow; CONTRIBUTING.md
untouched (separate task, per issue scope).

LOOP HARDENING (2026-07-26) — deterministic issue closure. The loop cleared its first
two real tasks fully autonomously (#37→PR #41, #38→PR #42, both merged by github-actions),
proving LE-5 build→gate→merge end to end. One reproducible gap surfaced: GitHub PARSED
each PR's `Closes #N` (`closingIssuesReferences` held the issue) but did NOT close it on
merge — a known failure mode for PRs merged by the github-actions app via native
auto-merge. Fix: `.github/workflows/loop-close-issues.yml` runs on `pull_request: closed`,
and on a real merge closes exactly the issues in GitHub's OWN `closingIssuesReferences`
(never a body regex — it can only close what GitHub linked as closing) and clears the loop
labels, so a resolved issue never lingers open+in-progress. Pinned by
`tests/test_loop_driver.py::TestLoopCloseIssuesWorkflow`.

WORK-SPINE CONSOLIDATION (2026-07-26) — one small ordered queue, agents work cleanly.
Founder: "sequential breakdown from a single source of truth as vertical slices + small
tasks; stop diverting/losing requirements; the doc must stay small (big = hallucination)."
Measured first: req↔trace diff proved NOTHING is lost — 48/48 FR+NFR traced in docs/04 to
real modules+tests (only X-03/X-05 lack rows: scope exclusions). Real cause of divergence
was 16 competing planning docs with no single sequential spine. Fix: new lean
docs/internal/QUEUE.md (~45 lines) — links (never copies) the sources (01 WHAT / 04 DONE /
09 HOW), holds only the ordered NOW/BLOCKED/PARKED queue + the anti-divergence Law (nothing
built that isn't a NOW task citing its FR/NFR; done = its 04 row updated same PR). NOW is
empty by design (frontier exhausted). docs/09-SDLC points to it; ROADMAP/KANBAN/PLAN/
07-ROADMAP banner-redirected for sequencing (detail retained). BACKLOG kept as the idea
parking lot the Law references.

## Issue #45 — reconcile stale deploy/launch status to verified ground truth (2026-07-26) — LE-5 loop:ready run

QUEUE.md and ROADMAP.md still called LE-2 continuous deploy HELD and branch protection an
open founder action, from before those actually landed — the loop and any human reading
either doc would work off a false "still blocked" picture. Re-verified each claim with its
own probe before touching docs (not trusted from the issue blindly): `curl -sS
https://staging.tokenops-cost-auditor.com/healthz` and the prod host both returned
`{"ok":true,"db":true,...}` directly — decisive, since a DB-connected live response is
only reachable through a deploy that used valid `DEPLOY_HOST`/`DEPLOY_DOMAIN`/
`DEPLOY_SSH_KEY` secrets, matching `deploy.yml`'s own post-deploy smoke step. For branch
protection: the `authorship`/`lint`/`type`/`test`/`docs` job names (ci.yml) and
`gate-round` (gate-round.yml) exist in the checked-in workflows, and 5 PRs merged into
`main` same-day (#40–#44) only through the gated auto-merge path, corroborating the
required-checks list is enforced. Could NOT independently re-query the live GitHub
Actions run history, environment secrets list, or the branch-protection API directly —
this agent's token (LOOP_PAT, per the LE-5 activation note above) is scoped to
contents+PR+issues only, by design, with no Actions/Environments/Secrets read access;
those specific sub-claims are recorded as corroborated-by-behavior rather than
API-confirmed, and a founder/admin-scoped token can re-run the exact `gh api
.../branches/main/protection` / `gh secret list` / `gh run list` probes to double-check.
Fixed: `docs/internal/QUEUE.md`'s BLOCKED section no longer lists LE-2 deploy or branch
protection as blocked (states LIVE, only the founder-gated prod promotion remains);
`docs/internal/ROADMAP.md` §3 and §4 — deploy secrets and branch protection moved to a
new DONE/LIVE subsection with their probes cited, §4's remaining pending list re-verified
line by line rather than copied forward. No workflow/code changes; `deploy.yml` untouched;
§5 untouched; no prod promotion attempted (founder-only manual dispatch).

LE-3 RECURSION-GUARD FIX (2026-07-26) — the loop's own merges now trigger deploy + close.
Verified defect: PRs #41-#46 were auto-merged by the github-actions app (GITHUB_TOKEN), and
GitHub's recursion guard SUPPRESSED all downstream workflows — so deploy.yml (on: push) never
deployed staging past #40 (cea49bfa), and loop-close-issues.yml (on: pull_request: closed)
never fired (#45 left open). Confirmed by mergedBy: #40 (human) deployed; #41-#46 (app) did
not. Impact was latent (the un-deployed commits were docs/workflows, no app code) but real.
Fix: auto-merge.yml enables auto-merge as the LOOP_PAT user (not GITHUB_TOKEN), so the
eventual merge is attributed to a real user and the merge-push triggers deploy + close.
Pinned by test_auto_merge_workflow::test_it_merges_as_the_loop_pat_so_downstream_workflows_trigger.

SECURITY HARDENING (2026-07-27) — loophole hunt + fixes. An adversarial hunt across
auth/session/RBAC/tenancy/FR-22 found the core layer SOUND (magic-link signed + single-use,
no privilege escalation, workspace-scoped reads, admin fail-closed, no prompt-text leak).
Two loopholes closed: (1) POST /copilot/seats ran an audit with NO authz.ensure(RUN_AUDITS)
— a viewer bypassed the run-audits gate that its twin POST /api/v1/audits enforces (the
connect-wizard bug class); added the matching gate. (2) the X-User-Email dev/test shim was
gated only by `app_env != "prod"` — a typo'd or staging env would open FULL impersonation;
now a fail-closed allowlist `_TEST_AUTH_ENVS = {dev, test}` so staging/`production`/unknown
refuse it. Pinned by test_rbac_journey::test_viewer_cannot_run_a_copilot_seat_audit and
test_auth::test_test_auth_shim_is_a_failclosed_allowlist. NOTE (flagged, not changed):
/copilot/seats is also unmetered (no payment_gate) — a business decision under money discipline.
REAL E2E JOURNEY TEST (2026-07-27) — closed the false-confidence gap. tests/test_journeys.py
only SEEDS an Audit row + checks rendering; it never walked the runtime, so the checkout
dead-end passed CI green and reached the founder ("breaks somewhere / losing info"). New
tests/test_e2e_real_journey.py walks the ACTUAL new-customer flow with NO X-User-Email shim:
real magic-link signup (/auth/signin-link → capture link → /auth/verify) → paid credit →
real POST /api/v1/audits that RUNS the pipeline → asserts status=done + valid_pct=100 +
findings>0 (real output) → /dashboard renders → /billing checkout STATE (config-aware:
asserts the Pay button when payment links are set, else the honest "switched on" dead-state).
A genuine break in signup/audit/report/checkout now FAILS CI instead of shipping green.

R-PLATFORM SLICE 2 — MCP SERVER (Issue #54, 2026-07-27). Shipped `tokenops-cost-auditor mcp`
(also `python -m tokenops_cost_auditor.mcp`): a stdio JSON-RPC MCP server so Claude Desktop/
Cursor/etc. can query TokenOps without leaving the editor. Design decision: it is a thin
urllib client over the EXISTING read API (`GET /api/v1/audits`, `GET /api/v1/audits/{id}/
findings`), authenticated with the same `TOKENOPS_COST_AUDITOR_TOKEN` bearer convention the
docs already teach — not an in-process caller of routes_api_read — so tenancy/scope
enforcement stays exactly where it already lives (web/api_auth) and is never duplicated
client-side; a scope-denied or missing/invalid token just surfaces the server's own error
text as an MCP `isError` tool result. Two read-only tools this slice (`list_audits`,
`list_findings`), no write tools per PLAN-SDK S-3. Docs: docs-site/api/mcp.md (install +
Claude Desktop/Cursor config + tool table), mkdocs nav. Pinned by tests/test_mcp.py (wire
contract: tools/list shape, tools/call happy path, missing-token/401/403/404 all fail clean,
unknown tool/method are JSON-RPC errors, full stdio round trip) + tests/test_docs_site.py::
TestMcpDocs. Engine untouched (mcp/ sits outside services/rules + services/pricing).

R-PLATFORM SLICE 3 — OUTBOUND WEBHOOKS (Issue #56, 2026-07-27). A workspace registers a URL
under Settings → Webhooks (O-2 `MANAGE_SOURCES` gate, mirroring routes_sources.py exactly:
the list is visible to every role, add/remove controls render only for owner/admin, a forged
POST fail-closes 403); on audit completion (hooked right after the existing `mail.report_ready`
call in `AuditRunner._pipeline`, migration 022 adds `webhook_endpoints` + `webhook_deliveries`)
we POST a signed `audit.completed` event to every active endpoint in that workspace. Design
decision: `services/webhooks/base.sign` mirrors the INBOUND `verify_signature` already in
`api/routes_webhooks.py` (raw HMAC-SHA256 hex digest of the exact body bytes) so the scheme is
symmetric and a receiver's verification code reads like our own inbound checks — sent as
`X-TokenOps-Signature` + `X-TokenOps-Event` headers. `WebhookEndpoint.secret` is stored
PLAINTEXT (not a one-way hash like every other credential in this codebase) because, unlike a
token we only ever verify, we must hold it to sign every future delivery; it is never
re-rendered after the shown-once creation response, and revoke NULLs it. Delivery is
best-effort by construction: `WebhookDispatcher` (`services/webhooks/dispatcher.py`) catches
its own exceptions, so a dead endpoint or network error can never fail the audit it reports on
— one attempt, a 5s timeout, the status recorded either way (no durable retry queue, out of
scope per the issue, noted for a later scaling slice). Payload is FR-22-clean by construction:
audit_id/workspace_id/status/total_spend_usd/projected_spend_usd/savings_pct/finding_count/
findings[{detector,severity,monthly_usd}] — never a prompt or completion. Docs:
docs-site/api/webhooks.md (payload schema + an `hmac.compare_digest` verification snippet),
mkdocs nav. Pinned by tests/test_webhooks_journey.py (real add-endpoint route → real audit run
→ captured delivery body/headers independently re-verified against the shown-once secret →
FR-22 marker-absence check → WebhookDelivery row → the Settings page shows the endpoint and
"200 ok"; a raising transport records a null status_code and the audit still reaches
status=done; RBAC: controls absent for a member + honest note, forged add/delete 403s) +
tests/test_docs_site.py::TestWebhooksDocs. Engine untouched (services/webhooks sits outside
services/rules + services/pricing, T-NFR-01 intact). X-01/X-02 SAFE throughout — observe-and-
notify only, never in the request path, never enforces anything on the customer's LLM traffic.

R-PLATFORM SLICE 4 — JS/TS SDK (2026-07-27). The official TypeScript SDK (sdk/js): counts-only
BY CONSTRUCTION (UsageRecord has no prompt/completion text field — FR-22), two credentials /
two capabilities (ingest key writes usage, read token reads audits+findings), zero runtime deps
(platform fetch). Built by hand — cross-ecosystem, the loop's pinned toolchain is Python-only:
verified locally with tsc strict typecheck + node --test (4 tests) + tsc build (dist/index.js +
.d.ts). New .github/workflows/sdk-js.yml (setup-node) validates it on any PR touching sdk/js.
Docs: docs-site/api/sdk-js.md + mkdocs nav. Mirrors the Python SDK's laws (observe-only,
X-01/X-02 safe). Python app toolchain unaffected (ruff/mypy/pytest all green).

R-PLATFORM SLICE 6 — GitHub Action (2026-07-27). action/ — a node20 GitHub Action that posts
the latest completed audit's findings (ranked by monthly $) to $GITHUB_STEP_SUMMARY, with an
optional fail-on-severity gate. Dependency-free (platform fetch + node:fs), READ-ONLY via a
read token, calls only GET /api/v1/audits + /audits/{id}/findings (no new server capability),
observe-only X-01/X-02 safe, FR-22 (counts/$/metadata, never text). run(deps) is DI-testable
(injected fetch/env/writeSummary/fail) + entry-guarded; dist/main.js is COMMITTED (Actions run
dist directly — root .gitignore un-ignores action/dist). sdk-js.yml generalized to a matrix
over [sdk/js, action]. docs-site/api/github-action.md + nav + TestGithubActionDocs + docs/04
traceability row. Built by hand (cross-ecosystem, in parallel to the loop's #59 metering slice
so neither blocks the other). Verified: tsc strict + node --test (3) + build; Python unaffected.

R-NAME-SEO §2 — the SEO/copy law (Issue #62, 2026-07-27). Audited every public (signed-out)
template for a bare "TokenOps" in title/meta-description/og:title/og:description — everything
already carried a qualifier ("Cost Auditor", "AI", "LLM", "spend", "cost") except one:
landing.html's og:title read "TokenOps Cost Auditor — by WitAura", which the FR-only allowlist
technically permitted (it already contains "Cost Auditor") but read as the bare brand name plus
attribution rather than an AI/LLM-cost sell, so it is now "TokenOps Cost Auditor — AI spend
audits, by WitAura" — same meaning, an explicit qualifier beyond the brand name itself. Copy-only,
no rename, no new page. Guarded by NEW tests/test_seo_copy.py: TestPublicRoutesRendered hits the
real routes (/, /sample, /legal/*, /login, /signup) through TestClient and pins the landing
description/og:title/og:description fields specifically; TestEveryPublicTemplateSource sweeps
every template outside app/ (authenticated, out of scope) and kit/ (component preview) at the
source level — including oauth consent/error, the web + PDF report, and invite/verify-confirm,
which need auth/session/oauth-request setup to reach live — so a future public page or a new
meta/OG field can't ship an unqualified "TokenOps" without a live route being wired for this
test. docs/04-TRACEABILITY.md row added. Engine untouched (templates-only change).

R-CATEGORY §2 / R-NAME-SEO §4 / R-COMPETITIVE-LEARN §3 — comparison strip category framing
(Issue #64, 2026-07-27). Enriched the landing comparison strip (`landing.html` `.land-compare`)
with the honest category framing from three rulings, categories only, never vendor product
names: added the missing rows (FinOps platforms, Consultancy audits, Observability) alongside
the existing Model routers / Gateways &amp; proxies / TokenOps rows. The FinOps-platforms row
names its real cost — a tagging program and an enterprise contract — against the TokenOps row's
self-serve, zero-integration, evidence-cited contrast. A new `hero-note`-styled line under the
table states the GPU-scope boundary plainly rather than hiding it: managed API token spend is
audited, GPU/training-compute cost is out of scope, a different audit. Copy-only; no new page,
no rename, no engine change. Guarded by NEW tests/test_seo_copy.py::TestComparisonStrip: every
category label renders through the real `/` route; the FinOps-platforms row names both
tagging and contract; the TokenOps row names self-serve; the GPU-scope line renders inside the
strip section; a short vendor-brand denylist (CloudZero, Kubecost, Apptio, Datadog, New Relic,
Honeycomb, LiteLLM, Portkey, Helicone, LangSmith, Braintrust, OpenAI, Anthropic) confirms none
appear in the strip. docs/04-TRACEABILITY.md row added.

R-PRICING-PAGE — dedicated /pricing page (Issue #66, 2026-07-27). `/pricing` 404'd; the only
pricing surface was landing's inline plans section, which mixes launch/list/anchor numbers in
one flow. Built a NEW `GET /pricing` route (`routes_pages.py::pricing_page`) + `pricing.html`
template rendering the SAME `services/payments/plans` catalogue and `plans.viewer_currency`/
`plans.launch_open` logic landing/billing already use — no reimplementation, no price VALUE
change. Each plan (Free/Pro/Scale) shows ONE effective price for the viewer's region; the
launch-cohort note and India billed-in-rupees note render exactly as they do on landing/billing;
one-off audit ($500/₹20,000/$199 India) is a separate, clearly labeled block instead of crammed
into the plan-cards flow. Per-plan checkout CTA is config-gated via `settings.checkout_link`
with the same honest "Checkout opens once billing is switched on." note as `/billing` when a
link is absent — never an invented link. Reachable: `_public_shell.html` nav + footer "Pricing"/
"Plans" links now point at `/pricing` (were `/#plans`), and a new "See full pricing →" CTA sits
in landing's plans section. Landing's inline pricing section itself is UNCHANGED (out of scope
per the issue — simplifying it to a link-only teaser is a separate slice). Guarded by NEW
tests/test_pricing_page.py: USD and INR effective-price rendering off the catalogue (not
literals), a no-jumble plan-card count, launch-note counts matching config, the currency toggle,
the one-shot price, nav+landing-CTA reachability, and checkout-link honesty both configured and
unconfigured. tests/test_pricing_final.py::TestConfigOnlyLaw's repo-wide inline-price sweep and
tests/test_seo_copy.py's template-source sweep both cover the new template automatically;
`/pricing` was also added to test_seo_copy's `TestPublicRoutesRendered.PAGES`. Engine untouched
(web/templates only); docs/04-TRACEABILITY.md row added.

Server-side geo detection — IP→country, zero cost (Issue #68, 2026-07-27). India→INR ($4.99)
was only reachable via a browser timezone-cookie JS or a hand-typed `?ccy=INR`; a first-time
non-India-timezone visitor never saw it. Built NEW `services/geo/resolver.py::country_for_request`
— a trusted proxy header (`CF-IPCountry`, configurable via `geo_country_header`, set by
Cloudflare's free tier) first, else a GeoIP lookup via `maxminddb` on the real client IP
(`X-Forwarded-For`'s first hop, else `request.client.host`) against a DB-IP Lite Country `.mmdb`
(free, CC-BY, no license key) IF `geoip_db_path` is configured and the file exists, else `None` —
never throws; a miss always falls through to USD. `services/payments/plans.pick_currency`/
`viewer_currency` swap `accept_language: str` for `country: str | None` at the SAME precedence
slot (explicit `?ccy` toggle > persisted toggle cookie > server-side geo > USD), wired at all
four render sites: `routes_pages.landing`/`pricing_page`, `routes_billing.billing_page`,
`routes_alerts.alerts_page`. RIPPED OUT the browser guessing it replaces: the timezone→cookie
`<script>` in `_public_shell.html` and the `"-in" in accept_language` branch in `pick_currency`
— the explicit `?ccy` toggle is untouched and still overrides everything. Config: `geo_country_header`
(default `CF-IPCountry`) + `geoip_db_path` (default `""`) in `config.py` + `.env.example`;
`maxminddb` added to `pyproject.toml`. `scripts/provision.sh` gained step 4d: downloads the free
DB-IP Lite Country db to `./geoip/` on the host every provision run (a live bind mount —
`docker-compose.yml` sets `GEOIP_DB_PATH=/geoip/dbip-country-lite.mmdb` directly, mirroring the
existing `PRICING_OVERLAY_PATH` pattern) — zero founder step; a failed/absent download leaves
`GEOIP_DB_PATH` pointing at a file that doesn't exist, which the resolver treats as a clean miss
(header path keeps working, deploy never fails on it). Guarded by NEW tests/test_geo.py
(`TestHeaderPath`: `CF-IPCountry` IN/US, no-signal→`None`, Cloudflare's `"XX"` unknown sentinel
treated as a miss, configurable header name; `TestGeoipDbPath`: mocked-reader country resolution,
`X-Forwarded-For` first-hop precedence over the proxy's own `client.host`, header-wins-over-db,
missing/corrupt db file degrades to `None` not a crash, a reader exception on a malformed IP is a
miss) + updated tests/test_pricing_final.py::TestOneCurrencyPerView (a REAL render of `/` under
`CF-IPCountry: IN` shows `$4.99/mo` on first paint with no cookie, `US` shows `$19/mo`, no-signal
defaults to USD, the `ccy` cookie still persists a prior explicit toggle — replaces the removed
Accept-Language/timezone-JS tests). Engine untouched (T-NFR-01 — `services/geo` is outside
`services/rules`/`services/pricing`); docs/04-TRACEABILITY.md row added.

Razorpay Standard Checkout for the one-shot INR audit (Issue #74, 2026-07-27). The
one-time audit purchase was sold via a hosted payment LINK, so `razorpay_key_id`/
`razorpay_key_secret` were dead config — never exercised end to end. Replaced the INR
one-shot purchase with the verified Standard Checkout flow: NEW `services/payments/
razorpay_orders.py::create_order` (httpx `POST /v1/orders`, HTTP Basic Auth
`key_id:key_secret`, amount in paise, `notes.email` — the order MUST be created
server-side first, since a payment with no `order_id` auto-refunds) + `verify_order_
signature` (HMAC-SHA256 of `"{order_id}|{payment_id}"` with `key_secret`, checked
against the checkout.js modal handler's callback). `services/payments/razorpay_link.py`
gained `OrderWebhookEvent`/`parse_order_event` for `order.paid`/`payment.captured`/
`payment.failed`, on the SAME FR-27 signature+timestamp rails as the existing
`payment_link.paid` parser. The webhook is the SOLE credit-grant authority (B1 — the
handler-payload signature check is UX only and never itself grants); the grant is
idempotent on `Payment.ref == order_id` (B3), so `order.paid` and a same-order
`payment.captured` (different event ids) or a re-delivered `order.paid` collapse to
exactly one credit — layered on top of the existing event-id dedup table.
`payment.failed` is an honest no-credit state (B4), never a 500. NEW `web/routes_
billing.py` routes: `POST /billing/razorpay/order` (O-2 `MANAGE_BILLING`-gated, 503
"checkout not switched on" when key/secret unset) + `POST /billing/razorpay/verify`.
`billing_page` now sets a `Content-Security-Policy` header allowing `checkout.razorpay.
com` (script-src/frame-src) and `api.razorpay.com` (connect-src) — the checkout modal
is an iframe and needs it; scoped to the billing page only, not app-wide, to avoid any
risk to the rest of the product's inline styles/scripts. `templates/app/billing.html`
gained a "Buy one-time audit" button for INR viewers only (USD stays on the existing
Stripe hosted link — a later mirror, out of scope here), wired to `checkout.razorpay.
com/v1/checkout.js`, with honest disabled/failure/dismiss states. Guarded by NEW
tests/test_razorpay_checkout.py (order-create request shape against a mocked httpx
boundary; real-HMAC signature verify valid/tampered; the full create-order→handler-
verify→signed-webhook journey proving the WEBHOOK grants the credit and it reflects in
a real upload unlock; idempotency across handler+redelivered-webhook and across
order.paid+payment.captured; the disabled honest state; a `@pytest.mark.integration`
test skipped unless `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are in the env, proving the
test key really works against api.razorpay.com when present). B5 (a `callback_url`
fallback for iframe-blocked browsers) parked to `docs/internal/BACKLOG.md` per the
issue. docs/04-TRACEABILITY.md row added.

**Post-#74 hardening (cold-reviewer #75 findings + recurring gate flake).** #74 merged
as PASS-WITH-NOTES; the re-run's cold-reviewer caught a REAL bug the mocked tests hid:
`create_razorpay_order` built a 53-char Razorpay `receipt` (`oneshot-{user_id:32}-…`),
but Razorpay caps `receipt` at 40 — every LIVE order would 400. Fixed to
`1x-{user_id[:8]}-{uuid:12}` (24 chars) + a `receipt[:40]` clamp in `create_order`
(defense-in-depth), and the mocked-boundary test now asserts `receipt`≤40 so it can't
regress. Also moved `authz.ensure(MANAGE_BILLING)` BEFORE the `session.commit()` so a
non-owner attempt leaves no orphan user row (RBAC-before-write). Separately, hardened
`scripts/gate_round.py`: the cold-reviewer twice (#69, #75) returned a bare `VERDICT:
FAIL` with no findings — a truncated response, not a valid TE-8 verdict, that blocked a
clean merge. `_run_agent_live` now retries a verdict-only reply once and, if it recurs,
records an honest NO-VERDICT "re-run" reason instead of a misleading FAIL (can never
mask a real FAIL — those carry findings). docs/04 row added.

Stripe Checkout Session for the one-shot USD audit (Issue #77, 2026-07-27). Mirror of
#74 for the USD path: the one-time audit purchase was sold via a static hosted payment
LINK, so `stripe_secret_key` was dead config. NEW `services/payments/stripe_checkout.
py::create_session` (httpx `POST /v1/checkout/sessions`, HTTP Basic Auth with the API
key as username/`""` password — accepts a secret `sk_test_` key OR a restricted
`rk_test_` key identically, form-encoded body, `unit_amount` in cents). The webhook
side needed NO new code: `checkout.session.completed` was already parsed by the
existing `StripeLinkAdapter`/`_credit` path (event-id-deduped, FR-27) from an earlier
slice, so this is pure session-creation + wiring, reusing that grant path unchanged.
NEW `web/routes_billing.py` `POST /billing/stripe/checkout` — creates the session
server-side first, then a 303 redirect straight to Stripe's hosted checkout page (no
iframe, no client JS, no CSP change); O-2 `MANAGE_BILLING`-gated before the commit
(same RBAC-before-write shape as the #75 fix), 503 "checkout not switched on" when the
key is unset. `templates/app/billing.html` gained a "Buy one-time audit" button for
non-INR (USD) viewers — a plain form POST, not JS — plus honest post-redirect banners
for `?checkout=success` (never grants anything itself — the webhook is the sole
authority) and `?checkout=cancelled`. Guarded by NEW tests/test_stripe_checkout.py
(session-create request shape against a mocked httpx boundary incl. the restricted-key
case; the full create-session→signed-webhook journey proving the WEBHOOK grants the
credit and it reflects in a real upload unlock; a bad signature grants nothing;
idempotency on a re-delivered event id; the disabled/cancelled/success honest states;
a `@pytest.mark.integration` test skipped unless `STRIPE_SECRET_KEY` is in the env).
docs/04-TRACEABILITY.md row added.

Razorpay Subscriptions checkout for recurring INR Pro/Scale (Issue #79, 2026-07-27).
Mirror of #74 for the RECURRING plans: the INR Pro/Scale subscription was sold via a
static hosted payment LINK, so a subscriber's card was never charged the exact plan
figure the plans page showed. NEW `services/payments/razorpay_subscriptions.py` —
`create_plan` (httpx `POST /v1/plans`, `item.amount` built from OUR pricing config
`plans.py::Plan.inr` in paise — the price-integrity rail, never a dashboard number) +
`create_subscription` (`POST /v1/subscriptions` against that `plan_id`, `total_count=
1200` ongoing, `notes.email`/`notes.plan`) + `verify_sub_signature`. The signature
gotcha (verified against razorpay.com's subscriptions integration guide): the
concatenation order is `payment_id|subscription_id` — payment_id FIRST — the OPPOSITE
of the one-time order's `order_id|payment_id`; razorpay-node issue #124 is exactly this
mixup, so a dedicated test builds a signature in the wrong (one-time) order and asserts
it is REJECTED. The webhook + state machine needed NO new code at all: `RAZORPAY_SUB_
EVENTS`, `razorpay_link.parse_subscription_event`, `subscriptions.apply_event` and the
dunning ladder (all WP-6) already existed and are reused completely unchanged —
`subscription.activated` remains the sole activation authority (B1), the handler-payload
verify is UX/auth only. NEW `web/routes_billing.py` `POST /billing/razorpay/subscription`
(creates plan+subscription server-side first, O-2 `MANAGE_BILLING`-gated before the
commit per the #75 RBAC-before-write shape, 503 when keys are unset, 400 on an unknown
plan) + `POST /billing/razorpay/subscription/verify`. `templates/app/billing.html` —
INR Pro/Scale rows now open the checkout.js modal against a `subscription_id` instead
of the old hosted link (one Subscribe button per plan); USD untouched (Stripe subs is
Slice D, out of scope). CSP reused unchanged from #74. Guarded by NEW tests/
test_razorpay_subscriptions.py (plan-amount price-integrity assertions for both tiers
against a mocked httpx boundary; the signature-order guard test; the full create-sub→
handler-verify→signed-webhook→activated-and-reflected-as-"current" journey; tampered
signature activates nothing; disabled/configured/already-subscribed honest states; a
`@pytest.mark.integration` test skipped unless the env keys are set). Mid-cycle plan
upgrade/downgrade parked to `docs/internal/BACKLOG.md` (cancel-and-resubscribe only
this slice, per the issue). docs/04-TRACEABILITY.md row added.
Gate-round #80 fixes (cold-reviewer): `TOTAL_COUNT` 1200→**100** — Razorpay caps a
MONTHLY plan's `total_count` at 100; the mocked boundary hid it and every live
subscription-create would have 4xx'd (same class as #75's receipt-40 bug). The test now
asserts `total_count`≤100 (real bound, not just equality-with-the-constant). The
`except ValueError, KeyError, TypeError:` flag was a FALSE POSITIVE — valid PEP 758 on
py3.14 (requires-python >=3.14), ENFORCED by ruff (parenthesizing is reverted by `ruff
format`), imports clean under the pinned toolchain; documented in the module docstring so
it stops being re-flagged.

Stripe Subscriptions checkout for recurring USD Pro/Team (Issue #81, 2026-07-27). Last
payment slice: mirror of #77 (one-shot USD) for the RECURRING Pro/Team plans — the last
piece was a static hosted payment LINK, so a subscriber's card was never charged the
exact plan figure the plans page showed. NEW `services/payments/stripe_subscriptions.
py::create_session` (httpx `POST /v1/checkout/sessions`, `mode=subscription`, an inline
`price_data` line item with `recurring[interval]=month`, `unit_amount` in cents built
from OUR pricing config `plans.py::Plan.usd` — the price-integrity rail, never a
dashboard number). The subtlety verified against Stripe's Checkout+Billing docs:
session-level `metadata` lives on the Session object, but the `customer.subscription.
created` webhook payload IS the Subscription object — only `subscription_data[metadata]`
propagates onto it, and its keys must be `email`/`plan` (not `user_email`) to match
exactly what the pre-existing `StripeLinkAdapter.parse_subscription_event` reads off the
subscription's metadata. Getting the key wrong would silently default every purchase to
"pro", under-granting Team — a dedicated test pins the exact key. The webhook + state
machine needed NO new code at all: `STRIPE_SUB_EVENTS`, `stripe_link.parse_subscription_
event`, `subscriptions.apply_event` and the dunning ladder (all WP-6) already existed and
are reused completely unchanged — `customer.subscription.created` remains the sole
activation authority (B1). NEW `web/routes_billing.py` `POST /billing/stripe/
subscription` (creates the session server-side first then a 303 redirect straight to
Stripe's hosted page — no iframe, no client JS, no CSP change, same idiom as `/stripe/
checkout`; O-2 `MANAGE_BILLING`-gated before the commit per the #75 RBAC-before-write
shape; 503 when the key is unset; 400 on an unknown/unpriced plan). `templates/app/
billing.html` — USD Pro/Team rows now POST a plain form (hidden `plan` field) to the new
endpoint instead of the old static per-plan hosted link; INR untouched (Razorpay subs
from #79/#80). The now-dead `checkout_links` context var removed from the billing route
(still used by the public `/pricing` page, unchanged, out of scope) — two tests in
tests/test_readiness_wave1.py that pinned the OLD static-link UI were updated to assert
the new dynamic-form UI instead. Guarded by NEW tests/test_stripe_subscriptions.py
(session-create request shape incl. `subscription_data[metadata]` keys against a mocked
httpx boundary, for both tiers — the price-integrity rail; the full create-session→
signed-webhook→activated-and-reflected-as-"current" journey; bad signature activates
nothing; idempotency on a re-delivered event id; disabled/configured/cancelled/already-
subscribed honest states; a `@pytest.mark.integration` test skipped unless
`STRIPE_SECRET_KEY` is in the env). Mid-cycle plan upgrade/downgrade parked to
`docs/internal/BACKLOG.md` (cancel-and-resubscribe only this slice, per the issue).
docs/04-TRACEABILITY.md row added.

Issue #83 (fast-follow to #72): `sdk/js` gained `getAudit(auditId)` — wraps the existing
`GET /api/v1/audits/{id}` with the read token (`read:audits`) and returns the parsed
`AuditSummary` body DIRECTLY, no envelope (unlike `listAudits`/`listFindings`, which unwrap
`.audits`/`.findings`). No new server capability, no auth change, no money-math touched
(`estimated_cost_usd` passes straight through). New `AuditSummary` interface mirrors the
route's real response shape exactly. Tests added to sdk/js/src/index.test.ts (fixture is a
byte-for-byte copy of the real `get_audit` body; missing-readToken-throws-before-fetch;
404 → `TokenOpsError.status === 404`; auditId URL-encoding) and
tests/test_docs_site.py::TestSdkJsDocs (getAudit + its endpoint documented).
docs-site/api/sdk-js.md and docs/04-TRACEABILITY.md (slice-7 row) updated in this commit.

Issue #85 (R-PLATFORM slice 8, fast-follow to #72/#83): the tokenomics breakdown became
an API capability. `services/dashboard/tokenomics.py` gained `load_artifact(report_dir,
audit_id)` — the exact absent/corrupt/purged-safe loader `routes_dashboard._load_tokenomics`
used inline, promoted so the HTML `/breakdown` page and the new read endpoint can't
disagree on when a breakdown exists; `_load_tokenomics` is now a thin delegation with its
signature unchanged, so `tests/test_breakdown.py`/`tests/test_drift_journey.py` pass
untouched. `web/routes_api_read.py` gained `GET /api/v1/audits/{id}/breakdown` — same
`read:audits` scope + tenancy path as `GET /api/v1/audits/{id}` (other-workspace id 404,
no new scope), the artifact's figures passed through VERBATIM (no parallel money math, no
golden owed). Absent/corrupt/pre-feature artifact → 200 with `breakdown: null` + an honest
`unavailable_reason`, never a 404/500/fabricated zero; a `_json_safe` walk coerces any
stray NaN/Infinity float to `null` (defense-in-depth against Starlette's `allow_nan=False`
500, not a known live bug). `sdk/js` gained `getBreakdown(auditId)` returning the WHOLE
typed response (`{audit_id, breakdown, unavailable_reason}` — not unwrapped, so a caller
keeps the honest-null reason). Docs: `docs-site/api/reference.md` (new section + the
null-breakdown contract), `docs-site/api/sdk-js.md` (table row + snippet), `endpoints.md`
regenerated (`scripts/export_openapi.py --check` clean). Parked to
`docs/internal/BACKLOG.md`: an MCP `get_breakdown` tool and cross-audit drift over the
API. docs/04-TRACEABILITY.md (slice-8 row) updated in this commit.

2026-07-28 (Fable session, post-#86 — requirements/design stage): #85→#86 verified merged
(verbatim-passthrough + honest-null both genuinely tested; endpoints.md regenerated, CI-proven).
Session rulings, all committed: QUEUE laws 5–6 (single flow — one line, one zone; session-start
reconcile; chat decision without an FR = lost scope); R-MODEL-FACTORY → FR-34..38 (docs/01 §H)
with HLD §8 + LLD §9 Fable design deltas (factory sibling repo, CohortExportEnvelope v1 k≥10,
ModelArtifactPort default-off, ShapeClass lens, RealizedDelta, showback CSV); R-REQ-PIPELINE
(docs/09 §9 + TE-5 amendment: Fable analyzes/designs → Opus 5 implements → Sonnet 5 unit-tests);
LIFECYCLE-MAP.md (completeness view; one ❓ = chargeback) + docs/README.md (internal front door);
T-D1/D2/D3 docs-maintenance candidates. Found + recorded, awaiting founder: authorship-squash
defect (LE-3 squash rewrites author + adds trailer; 65 commits since 07-24 violate rule 6;
pre-merge gate structurally blind to it) and the unrecorded R-SCOPE-STOP ruling — both now in
QUEUE BLOCKED ① – ⑤ with the sequencing/naming/chargeback decisions. Commits 897ff73, 95d319d.

2026-07-28 (same session, rulings round): founder resolved ①②④⑤ via in-session decision
round — T-D3 into NOW; R-SCOPE-STOP recorded as PARKED trigger (API/agent surfaces ← first
programmatic-access request); chargeback rejected-for-now; auto-merge flipped squash→rebase
(clean-authorship law — squash was rewriting author + adding a trailer on every merged
commit; repo allow_rebase_merge verified true). Open: ③ factory repo name (blocks T-F1 only).
T-D3 filed as a loop:ready issue this session.

2026-07-28 (R-ENT-DEPLOY design pass, Fable): docs/15-ENTERPRISE-DEPLOYMENT.md authored —
five deployment modes with honest readiness (CLI/SaaS/compose shipped; Helm/air-gap/
marketplace gaps trigger-named), two zero-touch lanes kept distinct (Lane A activation
bound to the verbatim R-DEPLOY-AUTOMATION 2 trigger; Lane B pull-only/N-1/zero-egress),
scale story from measured figures only (with the six-detector-era detect caveat and the
never-load-tested list stated), readiness ledger, Answer Sheet, HLD §6 + LLD §7 contracts.
Registered per R-REQ-PIPELINE: FR-39..42 (docs/01 §I), T-E1..E5 in QUEUE PARKED (triggers,
no dates), LIFECYCLE-MAP enterprise-deploy section. Zero build authorized. Reconcile notes:
the ruling's "docs/13-LIFECYCLE-MAP" = docs/internal/LIFECYCLE-MAP.md; perf page's "all six
detectors" label is stale vs nine shipped — re-measure gap flagged inside FR-42.

2026-07-28 (rule-6 absolute, founder-executed): history rewrite completed — 67 commits in
7a8d344^..HEAD rewritten (61 violating: author/committer normalized to Lokesh Prasanna
Kumar S, Co-authored-by/AI lines stripped; 6 clean commits reparented), 8 recorded SHAs
remapped in STATUS (07-27 precedent), force-push under temporarily-lifted protection,
protection restored (verified: force=false, 6 checks intact), remote verified by
scripts/check_authorship.py: 439/439 clean. Tags untouched (all in clean prefix). Forward
path already guarded by the rebase auto-merge flip. WitAura ownership noted; product name
stays TokenOps (R-NAME-SEO).

2026-07-28 (fresh session, spine reconcile + NOW sequencing): QUEUE law-6 reconcile ran
clean — zero open issues, HEAD = spine @ 9d98161, docs/04 tail consistent with shipped
slices. One stray found + fixed same-session: FR-34..38 and FR-39..42 were registered in
docs/01 (§H/§I) with no docs/04 rows (the matrix's own "any new FR requires a row" rule) —
two design-registered/unbuilt rows added, each shipping slice replaces its span. NOW order
decided (founder-delegated in the handoff prompt): T-F3 → T-F5 → T-F2 → T-D1 → T-D2;
T-F1 stays blocked on ruling ③ (factory repo name — the handoff placeholder came through
unfilled, so the name is STILL owed); T-F4 follows T-F3 with its scope-check first. T-F3
(FR-36 behaviour lens v1) filed as loop:ready Issue #89 with full docs/09 §2 acceptance
criteria: services/dashboard/shapes.py classifier per LLD §9.3, artifact-persisted shapes,
/breakdown chips (mockup before wiring, ux gate both depths), verbatim read-API
passthrough, honest coarse-depth degrade (findings-depth law), purity guard, Sonnet 5
unit-test authoring per TE-5. Builds run Opus 5 per R-REQ-PIPELINE.

2026-07-28 (T-F3 · FR-36 behaviour lens v1, Issue #89 — build session): SHIPPED, first
surface of the docs/12 dev-persona law. services/dashboard/shapes.py (LLD §9.3: five-class
deterministic ShapeClass classifier; thresholds shape_* in Settings mirror the D4/D6/D3/D2
detector family so the chip agrees with the findings list; precedence most-specific-first
burst→loop→growth→cache→steady; rationale = fixed counts-citing template). Additive
schema-versioned "shapes" block in tokenomics.json — write is guarded: a classification
failure logs and omits the block (honest null downstream), never fails a finished audit.
/breakdown gains the chip column (fix-first dev copy via SHAPE_COPY; owner money framing
byte-untouched), the pre-feature honest-null note, and the connected-source aggregate-depth
empty state — the old generic copy promised a breakdown a connected source can never
produce (source audits write no tokenomics.json); fixed in-slice per R-IMPROVISE, ux-gated.
Read API passes shapes verbatim (no endpoint change); sdk/js RouteShape + optional
AuditTokenomics.shapes + fixture; docs-site reference/how-it-works/sdk-js. Mockup gated
BEFORE wiring (PASS-WITH-NOTES; its WCAG f.8 came from the mockup's approximated hexes —
the real kit badge tokens measure 5.2–9.8:1, AA-clean, no kit change owed). Unit tests
authored on Sonnet 5 per TE-5/R-REQ-PIPELINE (18 tests: goldens ×5 exact class+rationale,
determinism/order-invariance, precedence, config injection, UAT-1 cache-exclusion,
FR-22 key-walk + fixed-template-only rationales). Notable catch: the SHIPPED FR-22 marker
tripwire (test_developer_platform fr22 shape tests) rejects the substring "prompt" anywhere
in a breakdown response — rationale vocabulary reworded to "input tokens" instead of
weakening the guard (recorded in shapes.py docstring). Full-suite tripwires hit + fixed:
.env.example SHAPE_* completeness; CSS design-source parity (the mockup-wiring-reconciles-
shipped-laws lesson, confirmed again). Gate round (all five): spec-guard PASS-WITH-NOTES
(empty-state copy note → closed by the ux gate's both-depths sign-off); cold-reviewer
PASS-WITH-NOTES, all 3 fixed in-diff (guarded compute_shapes; q=max(1,n//4) latent -0
slice bug; _shape_map drop now debug-logged); vv-engineer PASS-WITH-NOTES (shapes.py 100%
covered; coverage note closed by the final full run); ux-reviewer wired PASS-WITH-NOTES
(f.1 → .table-scroll wide-ledger affordance added, BOTH /breakdown tables wrapped);
system-tester first pass PARTIAL (it raced the main thread's concurrent gate-fix edits —
process lesson: freeze the tree before its walk), re-run on the stabilized tree
PASS-WITH-NOTES (live walk: 9/9 chip↔artifact route agreement, both honest states, links
resolve; its /reports 404 was a wrong-URL probe from the gate brief — no /reports route
exists, reports are per-audit artifacts; walkthrough suite is the destination authority
and is green). Full suite + coverage gate green (services 96.3%, money files 100%).
docs/04 FR-36 row split out of the FR-34..38 design span; QUEUE T-F3 NOW-line retired.
Next per NOW order: T-F5 (showback CSV); T-F4's scope-check may run.

2026-07-28 (same session, gate-home ruling): founder ruled the gate round's home is CI —
LE-4 has been live since 2026-07-25 (secret set; PRs #84/#86/#88 gated there) while this
session still hand-ran the five-gate round locally per the un-reconciled docs/09 §4 text,
duplicating the CI round. docs/09 §4 amended (CI is the reviewing home; build sessions do
tests/tripwires + PR only; ux mockup gate and card-named pre-wiring checks stay
in-session; system-tester post-deploy walk unchanged). The T-F3 local round stands as
this card's record — its cold-reviewer fixes landed pre-PR — but it is the last local round.

2026-07-28 (T-F5 · FR-38 showback CSV export, Issue #92 — build session): SHIPPED, first
card under the CI-gate-round regime (no local round; ux mockup gate stayed in-session per
the amended docs/09 §4). Session start found PR #91 (T-F3) UNMERGED — its CI gate-round
was still running and the auto-merge label was missing (every prior loop PR carried it);
label armed after confirming gate-round is a required branch-protection check, gate
passed, #91 rebase-merged, #89 closed. T-F5 then filed as Issue #92 with full §2 criteria
and registered in QUEUE NOW (docs(spine) 7618e50). The slice:
services/dashboard/showback.py (LLD §9.5 header verbatim; figures are the
tokenomics.json artifact's exact bytes — shortest-roundtrip float repr, never re-rounded,
reconciles to the tokenomics goldens byte-for-byte; fixed-template attribution caveat on
EVERY row so the coverage honesty survives the handoff into a spreadsheet; RFC 4180 CRLF;
empty allocation → header + one honest # comment line). GET /breakdown/showback.csv
behind O-2 MANAGE_BILLING (authz.ensure before commit, the routes_billing idiom; 403
non-owners; artifact absent/coarse-source/FR-21-purged → honest 404, never an empty 200).
/breakdown gains the owner-gated kit.button quiet affordance + a VISIBLE showback gloss
caption (non-billing roles see neither — O-2 absence idiom); i-download added identically
to icons.svg + _sprite.html (pin test). Mockup gated BEFORE wiring: PASS-WITH-NOTES, all
4 notes closed in-slice (f.1 trust claim visible-text not hover-only; f.2 delight
explicitly none — the designed care is the caveat riding every file row; f.3 resolved:
route IS the tag allocation, by_route groups by call tag, FR-38 "tag/route/model" names
provenance not a third grouping; f.4 "showback" glossed at first use). Unit tests
authored on Sonnet 5 per TE-5/R-REQ-PIPELINE (tests/test_showback.py, 16 tests: pinned
CSV-byte golden, empty-comment, json round-trip byte-verbatim property, caveat/order/
quoting, owner 200 + attachment filename, all non-billing roles 403, three 404 paths,
FR-22 marker-absence on the CSV, affordance visibility both roles + no-audit absence,
full upload→download journey). Full suite 1289 passed / 5 skipped; coverage gate green
(services 96.4%, money files 100%). No money-math change (serializer recomputes nothing)
→ no pricing golden / pricing_verify impact. docs/04 FR-38 row split out of the FR-34..38
design span; QUEUE T-F5 NOW-line retired; docs-site how-it-works "Show back" paragraph.
First CI gate-round on PR #93: spec-guard/system-tester/ux-reviewer/architect PASS;
vv-engineer PASS-WITH-NOTES, both notes closed in-diff (GUARDED_MODULES + showback.py;
docs/05 T-SHOW-01..13 block added in-slice, the wider FR-3x-era docs/05 backfill
registered as QUEUE candidate T-D5); cold-reviewer NO-VERDICT (truncated response twice —
harness fault, not a finding; re-runs on the fix push). CI lint caught test_showback.py
unformatted — ruff format is now part of the authoring checklist, not just ruff check.
Next per NOW order: T-F2; T-F4's scope-check may run.

2026-07-29 (T-F2 · FR-35 cohort export + consent, Issue #95 — build session): SHIPPED.
Session start verified #93 merged / #92 closed; found NO prod promotion dispatched yet —
staging carries T-F3/T-F5, the founder staging→prod review lane is still open. T-F2 filed
as Issue #95 with §2 criteria and registered in QUEUE NOW (docs(spine) 4ddeace). The
QUEUE-mandated scope-check ran at filing: flywheel/{frame,cohort,benchmarks}.py verified
NON-covering (frame = per-finding user-level R-F1 opt-OUT rows; FR-35 = aggregate-only
workspace-level explicit opt-IN) — the slice stood as scoped, reusing the pseudonym idiom
under a DISTINCT HKDF context, the L1 floor config, and frame's schema-self-audit
pattern. The slice: migration 024 workspaces.cohort_opt_in (NOT NULL default false);
services/flywheel/export.py (LLD §9.1 envelope verbatim; DETECTOR_KEYS is a LITERAL
nine-id tuple test-pinned to the registry because T-FLY-07/R-F4 forbids flywheel→engine
imports — the first full-suite run caught exactly that violation, fixed same-run; the
LLD's "d1..d10" is span notation, d7 never shipped; shape_mix passthrough from persisted
shapes blocks; k<10 → honest refusal naming n and the floor; deterministic; added to
T-NFR-01 GUARDED_MODULES); POST /settings/cohort behind MANAGE_WORKSPACE (owner-only,
audit-logged) + the owner-gated "Model improvement (cohort learning)" Settings card; GET
/admin/cohort-export.json (X-Admin-Token; below-floor 404 carrying the reason; every pull
audit-logged) + admin panel state row. ux mockup gate BEFORE wiring: PASS-WITH-NOTES, all
3 notes closed in-slice (f.1 the disambiguation-from-Peer-benchmarks now LEADS the
consent copy; f.2 mockup-only dimming flagged non-transferable; f.3 kit-tones-only at
wiring). Admin affordance wired to the panel's REAL idiom — bare header-token curl
actions, no kit button (the mockup's styled button was illustrative; recorded in the
mockup itself). Unit tests authored on Sonnet 5 per TE-5/R-REQ-PIPELINE
(tests/test_cohort_export.py, T-COH-01..12: pinned envelope golden incl. key order,
below-floor refusal, consent journey, RBAC absence+403, audit-log row, admin
404/200/token-gate, determinism, pseudonym-space disjointness, FR-22 marker-absence,
schema self-audit + registry pin, period discipline). Sonnet flagged tokenomics.py:142
`except json.JSONDecodeError, OSError:` — VALID under the pinned 3.14 interpreter
(PEP 758 tuple grammar), not a bug; noted in case the pin ever moves. No money-math
change (features are passthrough sums/ratios) → no pricing golden / pricing_verify
impact. Full suite green (1308 selected, exit 0); coverage gate green (services 96.4%,
money files coster/findings 100%); ruff + mypy + migration chain 001→024 all clean. docs/04 FR-35 row split out of the design span (residual row now FR-34+FR-37);
docs/05 T-COH block; endpoints.md regenerated (MP-3); QUEUE T-F2 NOW-line retired.
Next per NOW order: T-D1; T-F4's scope-check may run.

2026-07-29 (T-F2 gate round + note closure): PR #97 rebase-merged 19:25 UTC, first-run CI
gate round green in one pass — spec-guard/vv-engineer/system-tester/architect PASS (a
real cold-reviewer verdict again, no truncation); Issue #95 auto-closed; staging deploy
succeeded. cold-reviewer PASS-WITH-NOTES ×3 and ux-reviewer PASS-WITH-NOTES ×2, all five
triaged same-day in follow-up PR (fix/issue-95-gate-notes): c.1 off-pattern detector id
now WARN-logged, never a silent under-count (+ caplog test); c.2 export-time consent
confirmed AGAINST LLD §9.1 ("checked at export time" verbatim) — standing consent, not a
per-period ledger; documented in build()'s docstring as deliberate; c.3 per-workspace
query batching PARKED to BACKLOG one-liner (trigger: cohort well above the floor or a
measured slow export); u.1 "detector fire rates" jargon → "which cost patterns showed up
and how often" (mockup synced, the full what-leaves list intact); u.2 consent-card icon
detector→eye (existing sprite symbol — a consent surface shows what can be SEEN, not a
detector; no new tone, sprite-parity untouched).

2026-07-29 (T-D1 · internal-docs refresh, Issue #99 — build session): SHIPPED (PR open).
Session start verified #97/#98 merged + #95 closed; prod promotion still NOT dispatched —
staging carries T-F3/T-F5/T-F2 awaiting the founder's rendered-page review. The
QUEUE-mandated T-F4 SCOPE-CHECK ran first: the FR-37 realized-delta MECHANIC is already
shipped — savings.compute() credits each Applied finding min(max(0, baseline−recomputed),
baseline) at the next ≥7-day audit with honest pending/identified, and statements/build.py
inherits the figure — so T-F4 SHRINKS (not collapses) to the LLD §9.4 residue:
per-finding VerifiedLine(amount_usd, finding_ref, from_audit, to_audit) emission, the
attributed lines rendered in the statement VERIFIED section (provenance = both audit
ids), and the FR-37 acceptance journey test; totals must not move (existing goldens are
the tripwire). Recorded on the QUEUE T-F4 line (spine commit 3fc0c8c). T-D1 then filed
as Issue #99 with §2 criteria and registered in NOW. The slice: CODE-TOUR.md verified
stop-by-stop against the tree — Stop 3 agent-verified pricing (R-AUTO-PRICING,
pricing_verify.py) + the price file's REAL path (the old `data/prices.yaml` citation was
itself drift, caught by the new tripwire on its first run); Stop 4 rewritten for the nine
detectors (d1–d6/d8–d10, d7 never shipped, aggregate-coarseness caveat, detector_copy);
Stop 9 rewritten for Standard Checkout (plans free/pro/team, Orders/Checkout-Session
credits, subscriptions→entitlements(), atomic claim_credit unchanged); Stop 11 31 tables
/ chain 001→024; Stop 12 scripts list refreshed — plus four NEW Part-2 stops: 13 platform
API (SDK→ingest, scoped read API, OAuth-server+PKCE, MCP), 14 orgs/RBAC (tenant-blind
engine), 15 flywheel (L0 frame, ladder, FR-35 export), 16 statements (the ONE
verified-savings formula). docs/README.md reading-order note + known-stale register line
cleared. R-IMPROVISE in-slice: stale "six-detector" claims made count-free in TWO code
docstrings (sdk/__init__.py, routes_ingest.py) and PLATFORM.md §1 corrected to the nine;
PLAN-era docs (PLAN, PLAN-SDK, PLAN-COPILOT) keep their six-detector language as
era-accurate history, NOT drift; docs/01 FR-42 text + docs-site perf claims deliberately
untouched (T-D4 owns the re-time). Parked to BACKLOG (one line): tour stops for
dashboard/alerts/copilot/collector. New tests/test_docs_internal.py (authored Sonnet per
TE-5): cited-path existence, cited-symbol resolution, detector-count word pinned to
registry.DETECTORS (a d11 without a tour touch fails the suite), no literal six-detector
claims under src/. Full suite green — 1309 passed / 5 skipped, exit 0 (verified by
marker count; two earlier racing background runs were killed and re-run cleanly);
coverage gate green (services 96.4%, money files 100%). No money-math change, no
migration, no docs/04 row (spine/docs card, T-D3 class). Gate round: CI on the PR; no ux
gate (internal docs, no customer surface). Next per NOW order: T-F4 (shrunk scope above)
→ T-D2.

2026-07-29 (T-D1 gate round, PR #101): first run BLOCKED on a harness artifact —
cold-reviewer's response truncated twice, recorded NO-VERDICT; re-run came back green in
one pass (spec-guard/vv-engineer/system-tester PASS, cold-reviewer PASS-WITH-NOTES ×1).
The note, closed on the branch pre-merge: the tripwire's PATH_PREFIX_RE allowlist
silently excluded module-relative citations (web/…, api/…, services/…, persistence/…) —
exactly the drift class the test promises to catch. Fix inverts the approach: NO
allowlist — every backticked slash token is a path citation (product routes `/x` and
URLs excluded), resolved against four bases (repo root, package root, services/,
persistence/ stop contexts), `::symbol()` suffixes stripped; a moved file must now fail
at every base. The first widened run itself caught `/developer` being counted as a path
— the exclusion rule is evidence-driven, not guessed. Rounds 2–3 (same law, same day):
bare-filename citations (`subscriptions.py`) now resolved by package rglob, URL guard
widened to any `://` scheme, and `path::symbol()` citations split BEFORE the filter so
both halves verify (six tour citations previously had neither half checked). Round 4:
cold-reviewer finally clean, but system-tester FAIL — and rightly: the count-free
tripwire scanned only *.py, while findings.html's live empty state, landing.html,
_first_run, _savings, connect_wizard, tour.js and help_registry.yaml all still told
customers "six detectors" at nine — false confidence, the exact class T-D1 exists to
kill. Closure (TE-10, main thread): every customer surface made COUNT-FREE ("full-depth
audit" preserving the upload-vs-connected depth contrast; findings empty state "none of
our detectors"); the landing waste list gained the three missing kinds (d8/d9/d10 in
their DETECTOR_COPY plain voice) under a count-free heading; the tripwire now scans
*.py/*.html/*.js/*.yaml/yml for ANY spelled count beside "detector" — its first widened
run immediately caught two surfaces the gate had NOT cited (explore.html claiming "three
detectors could not run" when six now cannot; _waste_trend's "all six"), both fixed
count-free, plus export.py's own "NINE detectors" docstring. docs-site six-detector-era
copy (quickstart/reference/getting-started) stays deliberately untouched — T-D4 owns
docs-site; named in the tripwire docstring so it is parked, not dropped.


2026-07-29 (T-F4 · FR-37 realized-delta attribution, Issue #102 — build session): SHIPPED
(PR pending). Built to the SHRUNK scope recorded on the QUEUE line (spine 3fc0c8c): the
credit mechanic pre-existed, so the slice is pure attribution. savings.compute() now
emits SavingsSummary.verified_lines — one frozen VerifiedLine per credited route,
captured at the exact point the credit enters the headline (from_audit = R1
earliest-applied baseline audit, to_audit = the ≥7-day qualifying audit); `detector`
added to the LLD §9.4 shape (amended in-slice with rationale) because the ux gate's
jargon-law note required the statement to lead each line with DETECTOR_COPY plain copy,
which needs the key. statements/build.py renders the attributed lines in VERIFIED —
fixed explainer, plain-copy lead (off-registry detector falls back to raw id, visibly),
ref + BOTH short audit-id stamps in a parenthetical, shared _stamp() keeping line stamps
and the provenance list matchable by eye; zero-verified body untouched. Mockup
statement-verified-lines.html gated BEFORE wiring: PASS-WITH-NOTES ×3 (raw finding-id
jargon, AA contrast at 12.5px, delight-N/A unstated), all closed and re-gated to a clean
PASS. New fr37_before/after.jsonl fixture pair (gen_fixtures, zero RNG disturbance —
existing fixtures byte-identical): the only ≥7-observed-day fixtures in the tree, same
claude-sonnet-5 route, 32 uncached D2 repeats then cache-fixed traffic, so a real
pipeline re-audit genuinely qualifies (waste packs span 3 days and never can). FR-37
acceptance journey (test_fr37_journey.py): upload → D2 finding → applied via the real
feedback route → re-audit → statement issued via the real send route shows the
attributed line (HTML-escape gotcha: the plain copy's apostrophe renders as &#39; —
asserted on the unescaped body) + the honest applied-but-unproven pending state.
Unit tests T-VL-01..07 authored on Sonnet per TE-5 (emission fields, Σ==headline, R1
provenance, period discipline; rendering golden, zero-state, amount==headline). TOTALS
DID NOT MOVE: every pre-existing golden in test_verified_savings.py/test_statements.py
passed unchanged before any new test was added. docs: 04 FR-37 row split out (residual
row now FR-34 only), 05 T-VL block, LLD §9.4 amendment, QUEUE T-D1+T-F4 retired.
Pre-emptive note closure: the #101 round-6 cold-reviewer flagged (against code not in
that diff — extrapolated from the QUEUE line, but mathematically real for THIS slice)
that per-line cent rounding can drift a cent from the end-rounded headline on a
multi-line month. Closed here where the code lives via _reconciled_lines: headline
formula byte-identical (round of the unrounded sum, totals-must-not-move), lines
rounded individually with any residual cent landed on the largest line so Σ lines ==
headline EXACTLY; the reviewer's own suggested fix (accumulate rounded credits) was
REJECTED because it moves the headline in the same edge cases. Pinned by T-VL-09
(pathological sub-cent credits, hand-derived).
PARALLEL-IMPLEMENTATION RECONCILIATION: filing Issue #102 with loop:ready activated the
loop, and fb7d84b (loop session) shipped a leaner FR-37 directly to main at 07:43 —
4-field VerifiedLine (no detector), bare-ref statement copy ("finding D2-001", never
ux-gated — the jargon-law violation this slice's mockup gate had already ruled out),
per-line rounding WITH the Σ-drift defect, a seeded statement journey (the
false-confidence class from the 2026-07-27 founder ruling), and no docs/05/QUEUE
updates; it closed #102. This branch reconciles ON TOP of it (its commit stays in
history): my savings.py/build.py versions supersede (detector field, plain-copy lead,
_reconciled_lines, explainer sentence); their duplicate TestVerifiedLines class removed
(shadowed mine at collection) with its one unique case ADOPTED
(test_period_scoping_lands_the_line_in_the_proof_month, credited in its docstring);
their three statement tests removed as superseded — two pinned the un-gated bare-ref
copy, the third was the seeded journey replaced by the real-pipeline
test_fr37_journey.py. Nothing dropped silently; the union survives. Process lesson →
memory: never label an issue loop:ready while building it in-session.

2026-07-29 (T-F4 gate round, PR #104 + LE-4 harness outage): round 1 fell to a real CI
lint miss (ruff FORMAT check — the local pre-push ran `ruff check` only; both files
formatted, style commit) and rounds 1–2 both returned five instant [harness] OSErrors —
diagnosed from the runner log timing (all five within 1ms, twice, on fresh runners =
deterministic, pre-invocation): gate_round.py passed the whole prompt, embedding up to
200K chars of diff, as ONE `claude -p` argv element; the fr37 fixture pair (~350KB of
5,400-char repeated-prefix lines) pushed it past the kernel's 128 KiB MAX_ARG_STRLEN, so
execve died E2BIG before the CLI started. #101 never tripped it — its diffs were small;
the first fixture-carrying PR found the cap. Class-killed in scripts/gate_round.py on
the same branch: prompt on STDIN (uncapped; regression test pins that no argv element
scales with a 300KB diff) + generated fixture files excluded from the inlined diff and
NAMED for checkout reading instead (TE-2 budget; TE-3). Live stdin smoke + --dry-run
harness green; round 3 validates the fix by running on it. Round 3 (first REAL review
of the diff): all gates cleared — spec-guard/vv-engineer/architect PASS, two
PASS-WITH-NOTES triaged same-day on the branch: c.1 (cold-reviewer, real) a zero-dollar
credit — applied, re-measured, nothing saved — would render as a confident "$0.00 —
<saving claim>" under VERIFIED; closed with a RENDER-ONLY filter in build.py (summary
totals/counts and emitted lines untouched; dropping $0 entries cannot move Σ rendered
off the headline) + T-VL-10 pinning the mixed real+zero case, fixes_applied count
semantics deliberately left as pre-existing; st.1 (system-tester) live stdin smoke for
`claude -p` outside the mocked tests — already run in-session before the push (recorded
in the harness-fix commit), noted here as the closure. Round 4 (on the closures): all
cleared, PR #104 auto-merged 09:27 UTC, Issue #102's DoD now genuinely complete. Two
round-4 notes triaged same-day in follow-up (fix/issue-102-gate-notes): c.1
(cold-reviewer, real) the harness footer's name-only query spanned the whole fixtures
dir while the content exclusion stripped only the data globs, so gen_fixtures.py showed
BOTH inlined and "not inlined" in the same prompt — footer query now derived from
GENERATED_DIFF_EXCLUDES (single source, pinned in the harness test); vv.6 (explicitly
no-fix-requested) residual-on-largest-line at ≥3 lines → one BACKLOG line with its
trigger, per R-IMPROVISE no-silent-drop.

2026-07-29 (T-D2, Issue #106): docs/uml/ refreshed from the 2-diagram D6/D7 G4-sweep
set to 6 platform-era diagrams, every node/edge derived from the LIVE tree (route
tables, import graphs, module docstrings — grep-verified this session), never from a
spec snapshot. components.mmd redrawn package-truthful: web/ tenancy+authz boundary
(auth/authz/api_auth/api_scopes) drawn as its own subgraph, ENGINE CORE grouped and
labelled tenant-blind/role-blind (NFR-01 + R-ORG laws in the header), platform
services at package level, workspace-spine persistence, customer-side sdk/mcp/cli as
out-of-process consumers, external provider/factory sinks. audit-seq.mmd tail updated
(tokenomics.json + FR-36 shapes additive block, StageEvents, M-FLY-1 B1b benchmark
attach with honest-n alt, S-5 dispatch_audit_completed; FR-17 session auth replaces
the pre-D8 stub note). Four new sequences: read-api-seq (rt_/at_ resolution →
ReadPrincipal → scope → workspace-scoped read, MCP as same-door consumer),
payments-seq (both markets' Standard Checkout, FR-27 rail order, dunning ladder),
orgs-seq (invite→accept→membership, O-2 matrix, boundary-resolved tenancy),
flywheel-seq (R-Q9 verified loop → statement, L1/cohort/frame/FR-35 rungs with
consent + threshold alts). Validation: all six render green under mermaid-cli 11.16.0
(npx, pinned run this session); two mermaid lexer classes fixed during authoring —
bare `%%` comment lines break the flowchart parser, `;` in sequence message text acts
as a statement separator (replaced with em-dashes). No docs/04 row: T-D2 implements
no FR; diagrams are HLD/LLD conformance artifacts (architect charter). Gate round in
CI on the PR per LE-4. R-IMPROVISE in-slice: the first round ran WITHOUT the architect
gate — ARCHITECT_TRIGGER only matched services/ + persistence/models.py, so a
diagram-only diff (the architect's own artifact surface) drew no architect, and this
card's "D6/D13-style pass" DoD would have shipped reviewed by no one. Fixed in the
same PR: docs/uml/ added to ARCHITECT_TRIGGER with test
(test_architect_added_for_uml_diagrams); the re-run round must show all five gates.

2026-07-31 (pricing gate unblocked — R-AUTO-PRICING × R-LIVE-PRICING reconciled): main was RED and
every PR blocked, for a reason neither ruling anticipated. Diagnosis: `pricing_verify` checks the
EFFECTIVE table (base + machine overlay), but `prices.auto.yaml` is a gitignored RUNTIME artifact
and neither ci.yml nor deploy.yml ever ran `pricing_sync` — so CI verified the hand-authored base
against a live feed, while R-LIVE-PRICING states that base "is never touched". That gate was
therefore structurally guaranteed to go red on any upstream feed move, permanently, and the only
hand-fix available was the one edit the design forbids. Second, deeper conflict: gate 4 of
pricing_sync deliberately HOLDS a swing beyond ±60% ("a one-off feed glitch must not rewrite money
math") while pricing_verify demanded exact corroboration — so during a LEGITIMATE large price cut
the two rulings were mutually exclusive and the safety hold bricked shipping. FIX: (a) ci.yml and
deploy.yml now run `pricing_sync` before `pricing_verify`, materializing the overlay; (b) a
divergence beyond gate 4's threshold is classified `held` — reported loudly, non-fatal in CI,
because corroboration RAN and the divergence is known, which is not "unverified" in
R-AUTO-PRICING's sense; (c) deploy runs `--strict-held` and still refuses, because a held row means
a rate we ship in customer-facing reports knowingly diverges from source. A SUB-threshold
divergence stays a hard failure — that one means the sync did not run, a real defect. Live result:
gpt-5.6-terra (20% cut) now AUTO-APPLIES via the overlay; gpt-5.6-luna (80% cut) is HELD and named;
CI exit 0, deploy exit 1 until luna is confirmed at source. Correctness catch during the build: my
first `_worst_swing` measured all four rate components, but gate 4 measures INPUT and OUTPUT only —
that mismatch would have let the verifier call a row "held" that the sync would actually apply,
hiding a real failure behind a non-fatal verdict; now mirrored exactly and pinned by
test_04c. Two pre-existing tests changed meaning and were updated honestly rather than deleted:
test_04 now uses a sub-threshold divergence (its intent, "a mismatch is named and fails", intact)
and test_04b pins the held path in both CI and deploy modes. NOTE a latent trap found en route: the
pricing tests assume NO overlay exists (they build the feed at a pinned date while `main()` verifies
at today), so running `pricing_sync` locally before pytest makes them fail; CI is safe because
pytest runs BEFORE the new sync step, but that ordering is now load-bearing and should be made
explicit when LE-8 touches this area.


2026-07-31 (CORRECTION — the human price gate I reintroduced, removed; gate-4 holds now expire on
EVIDENCE): the founder caught it — "why I should confirm the price? there was no human gate needed
for prices?" Correct, and this was the SECOND time in one session I proposed a human confirming a
rate. R-AUTO-PRICING is unambiguous ("no human gate — it has to be done by the agent strictly
verifying") and my `--strict-held` flag put one straight back by failing deploy until someone
confirmed gpt-5.6-luna. REMOVED from pricing_verify and deploy.yml; a held row is now non-fatal
everywhere. But removing the flag alone would have left luna stale at 5x the real rate forever,
because the ORIGINAL design has no automatic exit from a hold either: gate 4 holds, daily_digest
alerts a human, and `write_status` only overwrites the latest payload — nothing tracked a held
candidate across runs, so the only escape the design left WAS a person. That is the real gap, and
it predates me. FIX: gate 4 now corroborates across runs. `read_status` carries a `held_streaks`
map; a candidate the feed reports IDENTICALLY on `HOLD_CORROBORATIONS`(=3) consecutive runs has
falsified the one-off-glitch hypothesis and is applied automatically, while a FLAPPING feed — a
different wild number each run — resets the streak to 1 and never accumulates, which is precisely
the case gate 4 exists to stop. Proven end to end, not asserted: three consecutive real syncs gave
held(1/3) → held(2/3) → APPLIED, after which pricing_verify reports 35/35 rows verified, exit 0,
with luna at 0.2/1.2 under a dated epoch and no human anywhere in the loop. Daily ofelia cadence
means a genuine cut now lands in ~3 days by itself. Pinned by three tests incl. the flapping-feed
case; docs/04 rows updated in the same commit.
2026-07-31 (LE-4 harness fix — a terse clean PASS could block a merge): PR #111's gate round
returned BLOCKED on `cold-reviewer — NO-VERDICT` ("returned a verdict with no findings twice"),
the rerun returned PASS with the diff byte-identical, and every other gate passed both times. That
is a harness defect, not a review. Root cause in `_looks_truncated`: it flagged ANY reply with
under 20 characters beyond the verdict token as truncated, retried once, and on a second terse
reply converted the verdict into a merge-blocking NO-VERDICT — so a reviewer with genuinely
nothing to report was punished for brevity. The reasoning that fixes it: truncation removes the
TAIL, and the TE-8 verdict line IS the tail, so a verdict token being PRESENT is evidence the reply
COMPLETED; and the charter demands numbered file:line findings only for NON-clean verdicts, so a
bare `VERDICT: PASS` owes no findings and is contractually valid. Bare FAIL / PASS-WITH-NOTES stay
truncated-and-retried — those are charter-invalid without findings and are the responses actually
observed on PRs #69/#75 — and an empty or verdict-less short reply stays truncated too (pinned by
test_short_reply_with_no_verdict_token_is_still_truncated, so shortness alone can never pass).
Note the pre-existing test suite had pinned bare FAIL and bare PASS-WITH-NOTES but never bare PASS,
which is exactly why the case slipped through; it is pinned now.
2026-07-31 (R-TRACE intake — docs/09 §9 R-REQ-PIPELINE, analysis only, no build): founder asks
"full traceability end to end for audit ... for auditing the requirements for humans" and
"internal UI tool for human viewing and validating the traceability, agile safe methodologies"
analyzed and registered as **LE-7/LE-8/LE-9** in docs/09 §6 + QUEUE candidates T-T1/T-T2/T-T3.
HOMING CORRECTION MADE BEFORE MERGE: the first draft of this ticket minted them as FR-43/44/45 in
docs/01 §J. That was wrong and self-contradictory — requirement-traceability tooling is SDLC/CI
tooling, the same class as the gate agents and coverage_gate.py, which per the docs/04 scope note
is governed by CLAUDE.md rule 7 + docs/09 and OWNS NO docs/04 ROW; as FRs, DoD item 10 would have
demanded a matrix row the matrix itself forbids. §J removed, scope re-homed to the LE track.
GROUNDED IN A MEASURED DEFECT, not a proposal: sweep of docs/04 against the live tree found 22 of
63 test ids resolve to NO collected test (T-RUL-D1-01..03 for FR-07 — a shipped core detector —
absent from BOTH tests/ and docs/05; T-PRC-04..05 declared in docs/05 but carried by no test;
T-VL-08 a hole in a contiguous T-VL-01..10 block), 3 requirements (FR-40/41/42) with no row, and
192 distinct test ids in tests/ of which docs/04 cites ~41 — so 148 tests are invisible to any
document and the up-direction barely exists. ROOT CAUSE is structural and now stated: DoD item 10
is the ONLY machine-checkable DoD item whose owner is a review (spec-guard) rather than a script,
while items 2/3/4/5/6/7/9/12 all have mechanical owners — the repo tooled its EXECUTION layer
(loop_status, gate_round, coverage_gate, pricing_verify, check_authorship) and left its
SPECIFICATION layer manual. Design: LE-7 moves the edge INTO the test as a registered marker so
docs/04 becomes derived; LE-8 gates the drift classes in CI incl. suspect-link detection (parent
content-hash change — the one control Doorstop has that pytest-native options lack); LE-9 is the
console — one scripts/trace.py serving a CLI, a generated static docs-site page, and a LOCAL
server-rendered htmx UI launched like `make preview`, carrying the bidirectional walk, a GENERATED
agile board (projecting QUEUE × issue/PR state, replacing KANBAN.md — stale since 2026-07-24) and
the six flow metrics from issue/PR timestamps with zero estimation. X-05 permits this: it was
relaxed 2026-07-20 to server-side rendering + htmx partials. Tool scan (verified, 2026) concluded
BUILD THIN: no standard exists for machine-readable req→test links (OTel's test namespace has no
requirement-id attribute); OpenFastTrace is healthy and GPL-3.0-clean for CLI use but costs a JVM
in CI and an id rename; Doorstop/StrictDoc want to own the requirement store; sphinx-needs is
Sphinx-only; pytest-requirements is one-directional. NOW stays empty: the founder sequences.
2026-07-31 (T-T1 · LE-7 — requirement-bound tests, built via the LE-5 loop, Issue #113): adopted
pytest-requirements (ADR-8, docs/02-HLD.md §5) — @pytest.mark.verifies_requirement("FR-nn") is now
the single source of the requirement<->test edge. tests/conftest.py adds a pytest_collection_modifyitems
guard: a marker naming an id absent from docs/01-REQUIREMENTS.md fails collection outright (proven by
a pytester probe, not just asserted). Backfilled markers across the core v1.0 matrix — test_ingest,
test_pricing, test_rules, test_api, test_auth, test_payments, test_lifecycle, test_exporter, test_cli,
test_runner, test_report_web, test_polish, test_ops_scripts, test_perf, test_smoke, test_pricing_age,
test_import_guard, test_explorer, test_spend_anomaly, test_cohort_export, test_shapes,
test_fr37_journey, test_showback, test_runs — covering every M-priority FR/NFR (FR-01..FR-33/35..38,
NFR-01..15) with at least one marked test, except a small, DECLARED (never silent) exemption set:
NFR-02/08/09 (manual ops drills, not pytest-collectible), NFR-04 (T-PERF-01 is @pytest.mark.perf,
excluded from the default -m 'not perf' run), and FR-34/39..42 (design-registered/unbuilt or
trigger-gated, zero build authorized per docs/04). tests/test_traceability.py is the new LE-7 tooling
owner (CLAUDE.md rule 7 — owns no docs/04 row, carries no marker itself): pins M-priority coverage,
a 250-test backfill floor (up from zero before this card), the tooling-owns-no-marker convention for
gate_round/loop_driver/loop_status/auto_merge_workflow/pricing_verify/pricing_sync, and four
pytester-isolated probes of the plugin's guarantees (self-registering marker, JUnit XML
requirement_id property, -m verifies_requirement selection, collect-only map-building). Full suite
(uv run pytest -m 'not perf') green at 1345 collected tests, 295 now carrying a requirement marker.
docs/05-TEST-PLAN.md §6 added (folds in T-D5) documenting the marker convention alongside the
existing T-XXX vocabulary. Out of scope, per the card: the CI gate (T-T2/LE-8) and the console
(T-T3/LE-9) — scripts/trace.py does not exist yet, built next.
