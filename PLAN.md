# PLAN.md — TokenOps Cost Auditor build plan (D1–D7 detailed, D8–D14 outline)

Status: **APPROVED by founder 2026-07-17, with rulings recorded below.**
Governing docs: docs/00–07, 09, 10. Gate protocol per docs/10-AGENT-HARNESS.md §3–4.
Author: Lokesh Prasanna Kumar S. Date: 2026-07-17.

---

## 0. Decisions of record

### 0.0 Platform vision (founder, 2026-07-20, GRAND CONSOLIDATED ORDER v2 — verbatim)

WitAura AI Agentic Engineering Governance Platform — an ecosystem, not a
report tool: INPUT (any form a customer's LLM usage exists) -> ANALYZE
(deterministic, evidence-cited) -> REPORT (dollar-ranked) -> ACT (fixes +
feedback) -> PREVENT (alerts, budgets, later real-time control) -> IMPROVE
(models learning from accumulated customer data). Buyer = the BUSINESS
OWNER; proof = VERIFIED SAVINGS; goal = the platform sits in the customer's
daily operations and justifies its subscription with money it demonstrably
saved. Three rings, strictly sequenced: SPEND (audit -> control plane),
DISCIPLINE (Build Health), COMPREHENSION (codebase retrofit). TokenOps Cost
Auditor (live) is ring one's wedge; v1.5 (Part D) converts it into the
recurring ecosystem product and starts the data flywheel.

[Companion: docs/12-FLYWHEEL.md (Part B — ingestion tiers, deterministic
judgment, learning ladder, four moats, R-STANDARDS).]

### 0.1 Founder rulings on §4 questions (2026-07-17, binding)

**R-Q1/Q2 GATE CADENCE — CONFIRMED by founder at D1 stop.** Gates fire only at
milestone-group boundaries — grouped rows gate ONCE, at the end of the group
(G2=end D3, G3=end D5, G4=end D7, G5=end D9). ux-reviewer window = D7–D9 inclusive;
architect UML emission at D6-architecture content happens at the G4 sweep (end of D7)
and at D13 — no dedicated architect run at D6. If D7 report work materially changes
component boundaries vs D6, that must be noted in the UML file header. Schedule in §2.

**R-Q3 PRICING SEED.** prices.yaml seeded from official OpenAI/Anthropic pricing pages
as of seed date; every entry carries `effective_from` + `# source_url:` comment. Golden
spreadsheet rows are founder-verified BEFORE the D2-D3 group gate runs — main thread
flags the founder when fixtures/pricing_golden.csv is ready for verification.

**R-Q4 CACHE RATES & D2 FORMULA.** Pricing schema carries FOUR rates per model:
`input, output, cache_write, cache_read`. D2 missing-cache savings is provider-aware:
`savings = repeats × cacheable_tokens × (input_rate − cache_read_rate)
         − est_writes × cacheable_tokens × (cache_write_rate − input_rate)`
where `est_writes` = one write per TTL window per unique prefix, conservatively
estimated from timestamps; if windows cannot be estimated, apply a **0.7 haircut** to
the estimate. Confidence label stays `conservative`. Documented in methodology appendix.

**R-Q5 CACHEABLE TOKENS.** Per bucket: verified common-prefix length when prefix-hash
evidence exists; otherwise `0.8 × min(prompt_tokens in bucket)` (fixed 20% suffix
haircut). Haircut documented in methodology appendix.

**R-Q6..Q12 DEFAULTS ACCEPTED, two guardrails:** (a) any default touching money math is
recorded in the golden spreadsheet **notes sheet** (applies to Q7 monthly extrapolation,
Q5/Q4 haircuts, Q6 prefix-hash length, Q10 bloat binning); (b) any default that
interacts with X-01..X-05 scope or FR-22 is ESCALATED to the founder, never defaulted.

**R-DEPS (founder, D1 stop).** Approved beyond the kickoff list: `pyyaml` (runtime,
D3 — FR-05 YAML pricing table) and `python-multipart` (runtime, D6 — FastAPI multipart
upload). `httpx` confirmed dev-only (TestClient). NO other dependency additions
without asking the founder first.

**R-ICP (founder, D1 stop — strategic update from docs/09b finding #2).** Primary ICP
is agent-fleet engineering teams (Claude Code/Codex logs on disk); log-exporter
scripts are FIRST-CLASS onboarding deliverables. Build consequences: (a) D2 adds a
documented Claude Code local-log exporter under `scripts/exporters/` with its own
fixture + test — new requirement FR-24 added to docs/01 with a traceability row
(founder amendment, approved); (b) D8 landing copy leads with the agent-fleet story;
(c) marketing stats policy per docs/09b §2: only the attributed 79%/98% figures are
used until dogfood numbers exist (docs/09 §6 amended accordingly).

**R-GOLDEN-C1..C4 (founder, 2026-07-17, golden-CSV verification corrections).**
(C1) GPT-5.6 family cache_write = 1.25x input (sol 6.25/terra 3.125/luna 1.25),
30-minute minimum cache life; zero-write-premium default restricted to GPT-5.5/5.4/
5.3 families; golden row G13 exercises the terra premium. (C2) gpt-5.3-codex
re-verified against source_url — explicitly listed, primary-source confidence.
(C3) v1 does NOT model OpenAI long-context surcharge (>272K: 2x input/1.5x output)
or regional data-residency multipliers (OpenAI post-Mar-2026 +10%; Anthropic
US-only 1.1x); the D7 report methodology appendix MUST state that spend estimates
are conservative floors (added to WP-D7 deliverables). (C4) D2 est_writes TTL
windows are per provider-family (config D2_TTL_WINDOWS: anthropic 300s, gpt-5.6
1800s; fallback D2_TTL_WINDOW_S), never a single global window.

**R-D1-MAP (founder, 2026-07-17, D1-detector frontier list + downgrade map).**
Data-driven in config, founder-maintained, entries dated like prices.yaml. Seeds:
Anthropic (within provider only): fable-5->opus-4-8; opus-4-8/4-7/4-6->sonnet-5
(current effective rate: intro to Aug 31, standard from Sep 1); opus-4-1/opus-4->
opus-4-8 (legacy uplift); sonnet-5/sonnet-4-6->haiku-4-5. OpenAI: gpt-5.5-pro/
gpt-5.4-pro->gpt-5.5; gpt-5.6-sol/gpt-5.5->gpt-5.6-terra; gpt-5.6-terra/gpt-5.4->
gpt-5.6-luna; gpt-5.4-mini->gpt-5.4-nano. RULES: (a) exactly ONE tier down, never
chained; (b) never cross providers; (c) savings at the suggested model's four-rate
card, confidence=estimated; (d) short-completion threshold stays LLD default
(p50 < 150 tok, config knob); (e) every D1 finding carries the caveat "model
suitability requires your own quality evaluation"; (f) unknown/unmapped frontier
models produce an informational finding with no savings number.

**R-API (founder, 2026-07-17, API hardening — spec'd before D6 lands).**
FR-25 /api/v1 route versioning; FR-26 idempotent uploads (Idempotency-Key,
201-then-200 replays, 7-day key retention with upload lifecycle); FR-27 webhook
timestamp tolerance (5 min) + processed-event-id dedup (append-only) atop HMAC;
NFR-12 rate-limit keying user-else-IP with Retry-After on 429; NFR-13
MAX_CONCURRENT_AUDITS admission (default 2, queued status + queue position);
NFR-14 uniform /api/v1 error envelope {error:{code,message,request_id}} rendered
in the docs-site API reference. Tests T-API-03..07, T-PAY-06..07, T-NFR-12
(docs/05 amended). Lands: FR-25/26 + NFR-12/13/14 at D6; FR-27 at D9. Still OUT
with recorded triggers (BACKLOG.md): API keys (first request = buying signal,
notify founder), queue/workers (cap saturation), orgs/SSO (first team customer),
SOC2 (procurement blocker).

**R-PRICING-OPS (founder, 2026-07-17, pricing-table operations, v1 scope).**
NFR-15 last_verified in prices.yaml + CI loud warning (never failure) at >14 days
+ digest age line (D10). FR-28 every report prints pricing version/last_verified +
unpriced-model count/list (D6 JSON, D7 PDF methodology). FR-29
scripts/pricing_refresh.py read-only diff tool (fetch source_urls -> candidate
rates -> human-readable diff; NEVER writes prices.yaml; weekly per runbook §8;
failures in digest; lands D10). Docs-site pricing page presents human-verified
versioned pricing as a TRUST FEATURE: live/scraped pricing refused for money math
by design.

**R-PRICING-AGENT (founder, 2026-07-17) — WP-P1.5, FIRST post-launch package
(week 3-4), NOT in D1-D14.** FR-29b pricing-watch pipeline (ops-side only):
ofelia crawl 2x/week of source_urls + LiteLLM model-prices JSON cross-check
tripwire; snapshots archived with hashes; candidates -> pricing_candidates table
(pending_review); admin side-by-side diff, one-click approve; approval writes
prices.yaml entry (effective_from + source), auto-drafts golden-row suggestion,
bumps last_verified. HARD RULES: no auto-approval path exists in code; crawler
has zero write access to prices.yaml; LLM-assisted extraction only into the
candidate queue; cross-check disagreements flagged, never auto-resolved; every
approval audit-logged with founder as actor.

**R-SEQ-D6D7 (founder, 2026-07-17).** Proceed with D6-D7 group now, incorporating
R-API D6 items and FR-28 into D7 report deliverables; python-multipart lands at
D6 (approved). D-DOCS starts after G4 passes. G4 = architect (+UML emission),
vv-engineer, ux-reviewer at end of D7; report verdicts WITH a dogfood-readiness
assessment for UAT-1.

**R-SEQ-UAT1 (founder, 2026-07-17).** UAT-1 is founder-executed NOW, in parallel
with the build (CLI path on real Claude Code logs). Founder feedback = a
mini-milestone with its own fixes before D11-D12 formal UAT; expected follow-ups:
verified pricing rows for older model generations, D4/D6 threshold calibration.
D8-D9 build proceeds immediately (incorporating the architect's repo-pattern
note); G5 at end of D9 as scheduled. D-DOCS starts AFTER G5 (so it can include
founder-approved dogfood numbers and single-source the D8 legal pages).
STANDING REMINDER: T-PERF-01 is nightly-only; at least one successful nightly
perf run must exist before D-DOCS fills the benchmarks page (MP-6 precondition).

**R-PAY HMAC FIXTURES.** T-PAY signature tests must use known-good HMAC fixtures
computed independently of the implementation under test (fixtures generated by a
standalone script/reference values, never by calling the code being tested).

**R-MP9 (founder, 2026-07-17).** Legal single-sourcing CONFIRMED as built: web
templates (templates/legal/*.html) are the authoritative masters; docs-site
mirrors with drift-failing sync tests (tests/test_docs_site.py). No rendering-
pipeline dependency. Do not flip.

**R-PERF-MANUAL (founder, 2026-07-17).** T-PERF-01 triggered manually now
rather than waiting for the nightly schedule (amends the R-SEQ-UAT1 nightly
precondition). On pass: fill MP-6 with measured numbers, machine spec stated,
and clear that MEASUREMENT-PENDING item.

**R-D11-12-PARTIAL (founder, 2026-07-17).** D11-D12 authorization is PARTIAL:
after the perf run, proceed with everything not requiring founder input — UAT
harness prep, export-instruction hardening, threshold-knob documentation, F7
perf fixture validation. UAT-1 itself is founder-executed by definition
(docs/05 §5); its exit criteria (zero embarrassing false positives; report
readable by a non-founder CTO in <10 minutes) CANNOT be self-certified. The
UAT-1/UAT-2 sign-off gate stays OPEN until the founder's dogfood report lands.

**R-PLAT-DESIGN-EARLY (founder, 2026-07-18, VPS-wait instruction).** Platform
design work brought forward while awaiting deploy infra: create the
witaura-ai-agentic-engineering-governance-platform SKELETON repo (sibling directory, own git history) with the
docs/11 §3 tree, per-package design READMEs, workspace pyproject stub, and
the detailed WP-PLAT-0 migration design (module→package map, dependency
rules, config seam options, acceptance procedure). ZERO v1 code moves; the
v1 repo remains authoritative and unrestructured; WP-PLAT-0 migration TIMING
UNCHANGED (week 3, post-D14, never before first customers).

**R-DEPLOY-AUTOMATION (founder, 2026-07-18).** (1) WP-DEPLOY-1 (may land with
D13 or immediately after): scripts/provision.sh + minimal Terraform module
deploy/tf/ targeting Hetzner AND any generic Ubuntu host via provider
variables — create/point at VM, harden (ufw, fail2ban, ssh-keys-only),
install docker, clone repo at a given tag, write .env from template,
compose up -d, run migrations, execute runbook smoke checklist, print
healthz. ONE command from clean provider account to serving TLS. Seed of the
R-MARKETPLACE IaC rung — provider-variable clean so the same structure
extends to AWS/Azure/GCP. (2) CD trigger recorded in BACKLOG: auto-deploy-
on-tag authorized only when (a) >1 app ships from the monorepo (post
WP-PLAT-0) or (b) deploy frequency exceeds 1/week for a month; until then
deploys are founder-initiated, one command, human-observed. (3) Provider:
Hetzner CX32-class first (live price verified at build), migration cost
engineered to near-zero by R-DEPLOYMENT-CONTRACT.

**R-PLATFORM-ARCH (founder, 2026-07-18) — approved architecture, recorded
verbatim as docs/11-PLATFORM-ARCHITECTURE.md.** WitAura AI Agentic Engineering Governance Platform: ONE platform monorepo with uv workspace packages (ruled: NOT
multi-repo) — packages/ (wa-core, wa-pricing, wa-detectors, wa-report,
wa-harness), apps/ (auditor, controlplane, buildhealth, comprehend),
exporters/, deploy/, ops/. Integration contracts C-1..C-7 (CallRecordFrame
lingua franca; only wa-pricing computes cost; evidence citations mandatory
platform-wide; FR-22 platform invariant; R-DEPLOYMENT-CONTRACT per app;
shared account model; wa-harness gates + traceability for every module).
Feature→module map in the doc §5 supersedes register-entry status — every
strategy item has a tree address. WP-PLAT-0 MIGRATION: week 3, immediately
AFTER D14 launch, never before first customers; v1 repo NOT restructured
pre-launch; acceptance gate = suite green + byte-identical golden report
JSON post-move; CLI/image/DB/product names unchanged (R-NAMING intact);
tag platform-v1.0.0. Platform NAME activates at the day-45 gate per R-BRAND.

**WP-COMPREHEND (founder, 2026-07-18) — founder codebase-fluency kit.** Docs
and drills only; ZERO application-code changes; parallel to the D13/D14
sequence, blocks nothing. Deliverables: (1) CODE-TOUR.md — plain-language
guided reading, ~12 modules in pipeline order, per module: two jargon-free
sentences, FR/NFR served, one function to read first, proving test file;
≤300 lines; every technical term defined inline on first use. (2)
DEBUGGING-PLAYBOOK.md — 8 likely production failures, each: symptom → where
to look (exact log event / SQL / healthz field) → local repro fixture →
pinning test → STOP-and-escalate rule; three universal commands copy-paste.
(3) TEACH protocol in CLAUDE.md item 8 ("TEACH: <module>" → teacher mode,
3 comprehension questions, STATUS.md curriculum log; runner → rules →
pricing, one/day). (4) Break-and-fix drills: 5-fault catalogue in runbook
§8b, STAGING only, post-D13, one/week for 5 weeks, results logged in
runbook. ACCEPTANCE BAR ("I can support customers"): founder can unassisted
(a) trace any report finding to its detector code and test, (b) diagnose 4
of 5 drill faults, (c) explain the audit pipeline aloud in plain language in
under 5 minutes.

**UAT-1 SIGN-OFF (founder, 2026-07-18).** Review sheet completed; both
docs/05 §5 exit criteria PASS (zero embarrassing false positives; report
readable by a non-founder CTO in <10 minutes). D13 unblocked per
R-SEQ-POST-SIGNOFF.

**R-GTM-CONTROL (founder, 2026-07-18, batch 2 — copy revision on the existing
D8 landing surface, not new scope).** Landing leads with the CONTROL narrative
("take control of AI spend"); the audit is framed explicitly as step one of a
prevention path and remains the ONLY purchasable product. A control-plane
early-access CTA (email capture only; no product promises, no dates) with
verbatim copy "AI spend control — APIs, agents, and AI seats." Signup counts
are Phase-2 trigger evidence; weekly count surfaces in the daily digest.
ux-reviewer re-checks only the changed copy blocks at the next scheduled
gate; no dedicated sweep.

**R-ENTERPRISE-SEAT (founder, 2026-07-18, batch 2).** The aggregate-mode audit
backlog item gains a second validated demand signal (enterprise seat-tool
governance: Copilot Enterprise credits/seats scenario) and is scoped in
BACKLOG.md as WP-P2-AGG with three layers (aggregate audit / policy-threshold
recommendations mapped to native enforcement levers / governance retainer).
Promotion still requires founder PRD amendment at the day-45 gate.

**R-DEPLOYMENT-CONTRACT (founder, 2026-07-18, batch 2 — governs ALL
Phase-2/enterprise design; full text in BACKLOG.md).** (1) single deployable
artifact placeable in any customer zone by their platform team; (2) zero
required egress — offline license files, telemetry opt-in only, no phone-home;
(3) no assumptions about customer DNS/proxy/internet/reachability beyond
documented component links; (4) bring-your-own Postgres/TLS/identity/storage;
(5) versioned offline install bundles for air-gapped delivery;
(6) auditability (append-only logs, deterministic outputs, published
methodology) maintained as enterprise requirements.

**R-ENTERPRISE-READY + R-MARKETPLACE (founder, 2026-07-18, batch 2).**
Recorded in the BACKLOG.md trigger register: Entra ID first for SSO
(SAML/OIDC, SCIM after; X-03 stands until first team customer); Phase-2
control-plane deployment requirements per R-DEPLOYMENT-CONTRACT;
CLI-inside-perimeter as the standing data-residency lead answer at all tiers;
cloud deployment ladder compose → Helm → marketplace listings with IaC
templates; user-model principle (employees are DATA SOURCES, never platform
users; reader seats ~5-50; scaling = data volume + policy-decision
throughput, never concurrent logins). Explicitly NOT building now: SSO,
marketplace listings, SOC2, questionnaire portal.

**R-UAT1-FIXES-ACCEPTED (founder, 2026-07-18).** All four UAT-1 dogfood defect
fixes accepted: D4 cache-active exclusion + completion-token fingerprint;
top-50 bounded rendering with explicit note (JSON complete);
effective_prompt_rate() tokens-priced-as-billed (golden blend recorded);
headline savings capped at monthly spend with verbatim METHODOLOGY disclosure.

**R-D6-AGG (founder, 2026-07-18).** D6 chatty-loop findings aggregate per
session/tag: ONE finding per session, monthly impact summed over its runs,
evidence sampled across constituent runs (≤20, counts only), run count stated
in the finding text; report.json retains per-run detail under the aggregated
finding. IDENTICAL per-session aggregation applies to D4. Golden updates
follow money-math discipline (expected counts/impacts + spreadsheet
derivations in the NOTES sheet).

**R-EQUIV-SPEND (founder, 2026-07-18 → docs/01 FR-30).** Whenever metered-API
billing cannot be assumed (e.g. Claude Code exports), the report header and
methodology carry verbatim: "Figures are API-equivalent token value; actual
billing depends on your plan." Also on the docs-site quickstart Claude Code
exporter path.

**R-SELF-AUDIT (founder, 2026-07-18) — WP-SELF, scheduled immediately after
D13 deploy (before/alongside D14).** Ops-side only; engine and X-01..X-05
untouched. (a) scripts/self_audit.py: exporter on THIS project's sessions →
CLI audit → append one row per run to self_audit/ledger.csv (date, sessions,
calls, observed API-equiv spend, findings by detector, est. monthly waste,
waste %) + archive report.json; manual/local-scheduler only, NOT part of the
product deployment. (b) docs-site "We audit ourselves" page (Engineering):
cumulative audited build cost, per-milestone waste trendline (chart from the
ledger at docs build; MEASUREMENT-PENDING until ≥3 ledger rows), the UAT-1
story incl. the 228% defect caught pre-launch, and the intervention
experiment (2-3 named UAT-1 recommendations applied to our own workflow,
before/after deltas once ≥2 post-intervention milestones exist). Mandatory
verbatim rails: the R-EQUIV-SPEND line; "n=1, uncontrolled — your logs are
the real test"; link to run the same audit. (c) Ledger rows are
money-adjacent: each published row requires a founder-verification tick,
logged like golden files. (d) D14 launch assets cite ONLY ledger-verified
numbers; the UAT-1 figures (26.2% waste, 13s on 158k calls, $5,289/mo est. on
$20.2k/mo API-equivalent) usable WITH the equiv-spend framing.
[SUPERSEDED 2026-07-18, UAT-D5: that figure set is DEAD everywhere — the
exporter double-counted events. Citable set, founder-approved post
machine-check: $8,757.75/mo API-equivalent, $2,846.62/mo est. waste, 32.5%,
67,095 unique calls from 159,571 events (58% duplicates), same equiv-spend
framing. Ledger row 1 verified 2026-07-17 (golden-notes verification log).]

**R-SEQ-POST-SIGNOFF (founder, 2026-07-18).** UAT-1 sign-off OPEN (awaits the
founder's completed review sheet + both docs/05 §5 exit-criteria checkboxes);
D13 blocked until it lands. After the D6/D4 aggregation merges, uat1 review
artifacts are REGENERATED so the founder's pass reviews shipping behavior.
Post-sign-off sequence: D13 deploy per runbook §2 (incl. VPS-hardware perf
validation + concurrency memory check: 2x max-size audits vs 8GB) →
ops-engineer D13 gate → WP-SELF → D14 launch.

**R-TOOLCHAIN (founder, 2026-07-17, harness amendment → docs/10 §2 TE-11 +
all six agent charters).** Any gate check that executes, compiles, lints, or
type-checks code MUST run through the project toolchain (`uv run ...` against
the pinned interpreter), never the sandbox/system python. A finding produced by
any other interpreter is invalid by definition. When a reviewer and the main
thread disagree on a toolchain-dependent fact, the pinned-toolchain reproduction
is authoritative; the resolution is recorded in STATUS.md. (Origin: G5
cold-reviewer false-positive — PEP 758 syntax judged under sandbox Python 3.13
while the project pins 3.14.)

**R-NAMING (founder, 2026-07-17, strengthened same day).** The full name is used
EVERYWHERE — dirs, files, code, not just display strings: Python package
`src/tokenops_cost_auditor/`, distribution `tokenops-cost-auditor`, compose project
name, DB name/user, container user, image tags, logger names, CLI command
`tokenops-cost-auditor`. Because docs/03-LLD.md §1 and FR-04 previously spelled the
short forms, their path/command strings were updated to match this ruling (docs/01
FR-04, docs/03 §1 tree, docs/04 coverage rule, ux-reviewer charter path) — flagged for
founder review at the D1 stop. Git authorship: Lokesh Prasanna Kumar S only; no
co-author trailers; no AI references in commit metadata.

**MARKET REFRESH (founder-requested 2026-07-17).** Deep multi-source market research
re-run before build start; report lands in docs/09b-MARKET-RESEARCH-REFRESH.md with a
marked recommendations section; PRD amendments remain founder-written (change control).

**R-CONNECT (founder, 2026-07-19) — supersedes the WP-P2-AGG tripwire; PRD
amendment recorded (docs/00 Amendments).** (1) WP-P2-AGG PROMOTED to
immediate post-polish build (est. 1-2 wks): "Connect OpenAI" / "Connect
Anthropic" flows — customer pastes an org/admin API key; usage pulled
server-side via the official Usage/Admin APIs; reduced detector set as
documented since D1; key handling: encrypted at rest, revocable, never
logged; UI parity with the upload flow. (2) WP-COLLECTOR registered (next
after AGG): pipx-installable watcher for Claude Code transcript dirs —
dedup per UAT-D5 law, counts-only by construction, scheduled ship to the
API (FR-26 idempotency); one command, zero code changes; the enterprise
fleet onboarding. (3) SDK/proxy remains Phase-2 control plane — X-01/X-02
intact for the audit product; recorded rationale: in-path components live
in the customer's VPC per the deployment contract, post-trust.
(4) Sequence: R-LAUNCH-POLISH + R-ONBOARD → walkthrough → launch thread
with Connect flows honestly ABSENT from claims → AGG build starts
immediately after. [Superseded on sequencing 2026-07-20: GRAND ORDER v2
delivers R-LAUNCH-POLISH + R-ONBOARD as v1.5 WP-7 and folds the Connect
build into v1.5 WP-1 — see the GRAND ORDER v2 block below.]

**R-DESIGN (founder, 2026-07-20) — UI/UX constitution, binding on v1.5
WP-2/WP-7 and every future platform surface.** Claude Code reads the
frontend-design skill before any template work; the ruling sets direction,
the skill sets craft. (1) PHILOSOPHY "the auditor's aesthetic": premium
audit report, not startup toy — calm, dense-but-ordered, numbers-first;
Stripe clarity + Big-4 gravity. BANNED: purple-gradient AI clichés,
glassmorphism, emoji in product UI, decorative illustration, dark-pattern
urgency. (2) TOKENS (one wa-design.css across landing/app/docs/PDF): serif
display numerals; clean sans UI; tabular-nums wherever money appears; warm
paper neutrals; ONE accent chosen once; semantic colors only beyond it
(green=verified savings, amber=estimate, red=waste/alert); money figures
are the most visually weighted objects on every screen; 8px grid; ~1100px
max content width; 1px-bordered cards; dark mode deferred (BACKLOG).
(3) THREE-SECOND RULE as acceptance test on every screen (what is this
screen · the one number · my next action); ux-reviewer charter AMENDED to
test exactly these; clarity overrides delight. (4) WORKFLOW SPECS a-i
verbatim in the founder order (first-run 3-step never-blank dashboard,
<3min to first audit; owner hierarchy verified-savings hero → trends →
top findings with inline L0 → sources health; finding card = one component
three renderers; web report executive strip + collapsible methodology,
CFO-printable; emails text-first number-in-subject one-CTA; settings
boring-on-purpose double-confirmed destructive; landing hero = bill-shock
question + REAL dashboard screenshot (screenshot truth, never mock), trust
strip linking proofs; empty/error/loading designed; WCAG AA floor).
(5) PROCESS: WP-2 begins with static HTML mockups (dashboard + finding
card + first-run, no logic) gated by ux-reviewer against the three-second
rule BEFORE wiring; PDF inherits wa-design.css print styles at WP-7.

**R-DESIGN-ADDENDUM (founder, 2026-07-20) — experience elevation; amends
R-DESIGN §1-2, all else stands.** (1) "Precision luxury": crisp layered
depth — multi-tier soft shadows on elevation (2-4 tiers), 1px inner-border
highlights, subtle surface tinting, large confident serif numerals; depth
= crisp layers NOT embossed neumorphism (banned: low-contrast emboss,
blurred-blob backgrounds). (2) MOTION (CSS-first, 150-250ms ease-out,
respects prefers-reduced-motion): NUMBER MOMENTS signature — hero
verified-savings counts up on load (600ms, once); marking Applied flows
the $ into the headline; card hover lift; evidence expanders spring;
audit progress = live pipeline strip with human status lines; htmx swaps
150ms fade + 4px rise; charts draw-in; press scale(0.98); success
checkmark draw; no toast storms. 3D BUDGET: exactly ONE hero element on
the landing page (CSS-perspective tilting dashboard screenshot), NOWHERE
in-app. (3) WOW-PER-WORKFLOW: one designed delight per flow, named.
(4) ACCEPTANCE: ux-reviewer checklist — every gated surface names its
delight and proves contrast + reduced-motion compliance; three-second
rule overrides on conflict. Scope note: R-DESIGN + addendum are DIRECTION
for surfaces inside frozen v1.5 scope — zero new features, zero dates.

**R-DESIGN-SHELL (founder mockup review, 2026-07-21) — supersedes the
single-page dashboard mockup; restructures V-D4 templates only (zero
features, zero dates; SSR + htmx partials law stands).** (1) APP SHELL:
left sidebar grouped by the ecosystem's own stages so navigation itself
explains the platform — MONITOR (Overview · Findings · Reports & Audits) /
CONNECT (Sources · Get your logs) / ACT (Alerts · Savings Statements) /
ACCOUNT (Settings · Billing) / ENGINEERING (Detector detail · Methodology);
obvious active state; collapsible on mobile; ONLY real shipped modules
appear — no "coming soon" anywhere (the no-promises law applies in-app;
the sidebar GROWS as rings ship, which is the platform story told
honestly). Slim topbar: product name · plan badge · data-freshness stamp
("data as of <last audit/pull, UTC>") · account menu. (2) OVERVIEW =
MODULAR WIDGET GRID, each a self-contained server-rendered partial:
W1 verified-savings hero (full width), W2 spend trend + W3 waste% trend
(pair), W4 top findings by $ with inline Applied/Dismissed, W5 sources
health, W6 next-audit countdown, W7 recent alerts, W8 latest Savings
Statement. EVERY widget carries title + one-line "What this tells you"
subtitle + provenance stamp (audit id / pull time) + designed empty state
that teaches the next action; independently htmx-refreshable. (3) THE
HOLISTIC SPINE — pipeline ribbon W0 at top of Overview: INPUT → ANALYZE →
REPORT → ACT → PREVENT drawn live from real state (sources connected,
last audit time, findings open, applied count, alerts armed); one glance =
end-to-end comprehension. (4) DETERMINISM AS A DESIGN FEATURE: no
skeleton-shimmer fakery; every number traceable to a stamped audit;
identical inputs render identical screens; Engineering tab says it plainly
("deterministic engine — same logs, same report, byte-identical");
freshness stamps everywhere money shows. (5) PROCESS: mockup v2 =
app-shell + Overview grid + ribbon; finding-card and first-run inherit the
shell (first-run renders INSIDE it with widgets in guided empty states);
ux-reviewer gates v2 per-widget against the three-second rule; then STOP
for founder review — wiring only after founder GO.

**R-DESIGN-V3 (founder mockup review #2, 2026-07-21) — enterprise polish +
in-product guidance. FINAL mockup round: v3 → founder verdict → wiring;
remaining polish handled as inline notes during V-D4, not further mockup
cycles.** (1) DENSITY & RICHNESS: (a) single inline-SVG stroke icon set
(lucide-style, self-hosted sprite, ~20 icons) on sidebar/widget
headers/stat chips/alert types — no emoji, no icon fonts; (b) REAL charts
in mockups (spend = area with gridlines + axis labels, waste% = line with
target band, sparklines in stat chips) — placeholder boxes BANNED;
(c) density pass: tightened topbar/sidebar, findings as a sortable data
TABLE with the card as expanded state, number-first stat-chip row under
the hero, type scale up (h1 22px, widget titles 15px/600 with icons,
hero larger); (d) chrome: sidebar surface tint vs paper page, active-item
accent bar, topbar hairline + lift-1, consistent 12px provenance meta.
(2) IN-PRODUCT GUIDANCE — real feature, ADDED TO WP-2 SCOPE as V-D4g
(+1 day, founder-accepted): (a) guided tour, 5 sequential spotlight steps
(ribbon → hero → findings/Apply → sources → alerts), positioned popovers
with Next/Skip, progressive vanilla JS + CSS (no library, no SPA),
dismiss state persisted server-side, replayable from Help; (b) per-widget
"?" help popovers (what it shows · where the number comes from in words ·
what to do with it · Learn more → docs-site), content authored ONCE in a
YAML help registry rendered SSR so docs and popovers cannot drift;
(c) HELP sidebar group — Guide pages (How TokenOps works · Your first
audit · Applying findings · Reading your Savings Statement, one screen
each) + Replay tour + docs link; (d) workflow breadcrumbs (step 1 of 3)
with the current step's purpose in a sentence. (3) Guardrails unchanged:
banned list stands, determinism stamps stay, three-second rule judged
WITH help affordances present, WCAG AA on all new chrome. (4) GATE:
ux-reviewer on v3, then founder three-second review; deliverables =
overview, findings-table, first-run-with-tour-step-1.

**R-PERSONA (founder, 2026-07-21) — design law; applied during V-D4 wiring
as copy/structure discipline. NO new mockup round (the v3 verdict remains
the gate).** (1) THREE-DEPTH RULE on every surface: each widget/page must
read correctly at three depths — (a) HEADLINE, the layman/owner sentence:
plain words, a money number, zero jargon; (b) CONTEXT, the manager line:
what changed, since when, provenance in words; (c) DEPTH, the engineer
expander/tab: evidence tables, detector params, methodology links.
ux-reviewer checks ALL THREE depths per surface at wiring gates.
(2) JARGON LAW: detector names never appear at depth (a) — "You're paying
full price for prompts you resend", never "D2 missing-cache". Technical
identifiers live at depth (c) only; the help-registry YAML carries BOTH
phrasings so popovers translate between personas. (3) AUDIENCE TAGS: each
Guide page opens with "who this is for" (Owner · Engineer · Both), same
discipline as the docs site. (4) ARCHITECT LENS registered, NOT built:
per-agent / per-pipeline / per-knowledge-base attribution views are the
T4-era architect dashboard (R-AGENTIC-DIMENSIONS + R-RAG already reserve
the span dimensions); BACKLOG line added; arrives with T4 data, not
before. (5) Savings Statement stays the owner artifact; report PDF stays
the shared artifact; NO persona-forked dashboards — one shell, three
depths, forever.

**R-CLARITY (founder, 2026-07-21) — addendum to R-PERSONA; applied during
V-D4 wiring, no mockup round.** (1) DEVELOPER DEPTH IS DESIGNED, NOT
DUMPED: depth (c) on every finding answers, IN ORDER — WHY flagged (the
rule in one sentence + its threshold values) · EVIDENCE (the counts
table) · THE FIX (copyable snippet or exact config change, per finding
type) · VERIFY (what the next audit will show if applied) · methodology
link. A developer with zero FinOps knowledge and an owner with zero
engineering knowledge must EACH find their complete answer on the same
screen at their own depth. The help-registry YAML gains a why/fix/verify
triple per detector. (2) FAMILIARITY PRINCIPLE: workflows adopt the
conventions of the dashboards our users already live in (the
Stripe/Datadog/Grafana grammar) — filters top-left, time-range top-right,
row→drawer expansion, sortable headers with aria-sort, breadcrumbed
multi-step flows, settings as grouped forms. The novelty budget stays
spent on the pipeline ribbon + the double rule ONLY; every other
interaction should feel pre-learned. ux-reviewer check 9: "any
interaction pattern a Datadog/Stripe user wouldn't already know is a
finding." (3) SECTION PURPOSE LINES: every sidebar destination opens with
one plain sentence of "what you do here" (sourced from the help
registry) — the ecosystem's workflow made legible page by page.

**R-MAGIC-CONNECT (founder, 2026-07-22) — WP-7 scope detail; +0.5 day
absorbed in the polish milestone already in plan.** (1) GUIDED KEY WIZARD:
Connect becomes a hand-held 3-step wizard per provider — (a) "Open your
provider's key page" as a deep-link button to the exact console screen,
with an annotated ILLUSTRATION beside it showing precisely what to click
and which permission to pick (read-only/usage scope). [AMENDED by
R-WIZ-ILLUSTRATION, founder 2026-07-23: a DRAWN, diffable SVG replaces the
original "annotated screenshot" — a PNG of a provider's UI rots silently on
their next restyle; a drawn illustration is version-controlled and
reviewable.] (b) paste field with LIVE
validation — on paste we test the key server-side immediately and show
"✓ Connected — we can see your usage (read-only). We can never see prompts
or make calls." or a plain-words error ("this key can't read usage — here's
the screenshot of the right permission"); (c) done-state setting
expectations in one line: "First audit tonight. Your dashboard fills by
morning. Nothing else to do — ever." (2) INSTANT GRATIFICATION PULL: on
successful connect, fire an immediate first pull + mini-audit in the
background rather than waiting for the nightly tick, so the dashboard shows
real numbers within minutes — the magic moment is THE FIRST SESSION, not
tomorrow. (3) COPY LAW for the wizard: zero jargon (never "org admin key";
say "a read-only key to your usage reports"), every screenshot
current-version, wizard help keys live in the registry (T-HELP coverage
applies). (4) CONCIERGE FALLBACK recorded in the GTM register, NOT built:
for early customers, "book 10 minutes, we do it on a call with you" — the
solo-founder superpower incumbents cannot offer. (5) REGISTERED, NOT BUILT:
provider OAuth adoption tripwire — the day OpenAI/Anthropic ship OAuth for
usage scopes it promotes immediately as the sign-in path; until then the
wizard IS the state of the art.

**R-STMT-MONTH (founder, 2026-07-22) — ratifies the V-D6 default as LAW.**
Verified savings credit to the month of the PROVING audit; pending belongs
to the month the fix was applied. Rationale adopted verbatim: a sent
statement is an archived artifact and must be true when written, never
restated. The single compute() with a period filter is confirmed as the
ONLY implementation — a second copy of that formula is forbidden forever.

**R-COVERAGE-DEBT (founder, 2026-07-22).** services/mail/smtp.py (83.8%)
and services/lifecycle/purge.py (78.9%) CARRY as recorded debt — declining
to expand a frozen milestone was the correct call. Close them inside
V-D10's final sweep ONLY if the day has slack; otherwise they transfer to
BACKLOG with their numbers. Debt recorded beats scope creep every time.

**R-WIZ-DEGRADE (founder, 2026-07-22) — answers the V-D9 wizard question.**
Graceful degrade APPROVED: a provider unreachable at validation means the
key is saved with a plain-words "we couldn't reach your provider just now;
we'll validate on the first pull" state plus a retry affordance. Hard-fail
REJECTED — a customer's first minute must never hang on OpenAI's status
page. T-WIZ-05 covers the degrade path.

**R-NORMALIZE-AT-EVERY-DOOR (founder, 2026-07-23) — permanent law.**
Identity fields (email, event ids, route keys) are normalized IDENTICALLY at
every read and write path. A lookup that can miss its own insert is the bug
class — it produced a paid upgrade stuck in an infinite provider-retry loop
(V-D8 f.1). Pinned by the mixed-case email test.

**R-BATCH-SEND-ISOLATION (founder, 2026-07-23) — cross-cutting law.** Any
loop that sends to multiple customers commits and isolates per iteration.
Named after the repeat offence: the same defect appeared in alerts (V-D5
f.2) and again in dunning (V-D8 f.4). Applies everywhere, forever.

**R-SKILL (founder, 2026-07-23) — BACKLOG only, zero v1.5 change.**
(1) WP-SKILL: a "tokenops-audit" Claude Code skill wrapping the T1 exporter
and CLI, running locally on the user's own transcripts and transmitting
nothing; trigger = immediately post-v1.5 launch (est. 1 day). (2) WP-MCP:
an MCP server over /api/v1, triggered by the EXISTING API-key buying signal
— same event, modern surface. (3) Marketing line registered: "Install the
auditor inside the agent that's burning the tokens."

**R-LOOK-FINAL (founder, 2026-07-25) — THE LOOK DECISION, FINAL UNTIL DAY-45.
Ends aesthetic re-litigation; every review from here judges CLARITY and
FUNCTION only.** (1) The v6 ultra-modern hybrid ships as the DEFAULT mood
"sanchaya" (warm light): neumorphic depth on CONTROLS AND WIDGETS per the
family constitution's own clause; DATA SURFACES FLAT-CRISP — tables, charts,
evidence expanders and every money figure stay flat, high-contrast,
tabular-nums, because a bevel eats the edge of a numeral and money legibility
is the one thing this product cannot trade. (2) MOODS: sanchaya default, AURA
(dark) SHIPS AT LAUNCH as a value sheet + AA re-verification with a visible
topbar toggle; "Ledger" retained as an archived value sheet; Awaaz NOT adopted
(no voice surface in this product) — its editorial tone informs EmptyState copy
only. (3) NON-NEGOTIABLES, mood-independent and test-enforced: AA in every mood;
semantic colour law (verified=green, estimate=amber, waste=red — values remap
per mood, MEANINGS NEVER); the three signatures survive re-skinning (pipeline
ribbon, accountant's double rule under verified totals, Applied→headline
money-flow); honest states (EmptyState teaches, ErrorState says what happened
and what to do, money never shimmers); motion always has a reduced-motion
equivalent and meaning is never carried by motion alone.

**SUPERSESSION RECORDED:** R-DESIGN's AESTHETIC sections (auditor's-paper
austerity) are formally superseded by R-LOOK-FINAL. Rationale, founder's:
founder conviction is a launch asset, and the role-token architecture landed by
R-DESIGN-TOKENS-2 makes the swap safe — the look changed by editing values in
one block, with zero component changes and a green suite. R-DESIGN's
NON-aesthetic law (three-second rule, three-depth rule, jargon law, familiarity
principle, banned dark patterns, WCAG floor) survives untouched. v4 and v5 are
ARCHIVED EXPLORATIONS, retained in design/mockups/ for the record.
THE DESIGN SYSTEM IS NOW: one role map · one kit · moods as values · sanchaya
default.
APPLIED 2026-07-25: token values swapped to sanchaya + aura sheets over the
existing roles; --control-depth / --control-depth-pressed split from the
flat-crisp --lift tiers; divergence test re-scoped to fail paired-inset on
data/money/table selectors while exempting controls; AA now COMPUTED per mood
(it caught white-on-violet at 4.36:1 in aura — accent darkened to #6f4ff5,
5.11:1); mood token-name symmetry pinned (it caught --radius declared in one
mood only); semantic colour law pinned by hue dominance. design/moods/ledger.css
archived.

**R-DESIGN-TOKENS-2 (founder, 2026-07-25) — design-system constitution
upgrade, adapted from the WitAura family design language. Applies at
v15-ui-unify wiring + R-LANDING-2. No new mockup round; NO visual re-theme —
this formalizes the architecture UNDER the approved look.** (1) ONE TOKEN MAP,
SEMANTIC ROLES: ~12 role tokens (ground, surface, surface-raised, ink,
ink-soft, rule, accent, money, verified, estimate, waste, lift tiers);
components reference roles only; a hex outside the token block FAILS a test.
Neumorphic depth roles explicitly NOT adopted — recorded divergence, money
legibility outranks family consistency. (2) MOODS AS VALUE SWAPS: theming is a
data-mood attribute swapping VALUES, never a re-theme. ONE mood ships now,
"Ledger" (warm-paper auditor's light); "Night Audit" moves from
BACKLOG-someday to BACKLOG-DESIGNED — a token-value sheet plus AA
re-verification, zero component changes by construction. (3) ONE COMPONENT KIT
— screens compose, never invent; Skeleton BANNED for numbers (money never
shimmers; use explicit "computing…" language). A bespoke element is a
ux-reviewer finding. (4) THE SIGNATURE, one glance away on every app screen:
pipeline ribbon + accountant's double rule under any verified total +
Applied→headline money-flow. Nothing else competes for signature status.
(5) AUTHORITY LIVES ON THE SERVER: UI paints decisions, never makes them —
(a) absent capabilities are OMITTED from the payload, (b) plan-locked features
are honest upsells never fake-enabled, (c) every money-affecting mutation is
explicit-confirm with the consequence in words (R-VERDICT-EXPLICIT
generalized), (d) htmx endpoints re-check authority server-side always.
(6) A11Y + I18N FLOOR: AA in every mood; depth never carries meaning alone;
motion always has a reduced-motion equivalent carrying the SAME information;
all UI strings become translation keys at wiring (en only shipped). Indic
locales → BACKLOG. ux-reviewer charter gains role-token compliance,
kit-composition, signature-presence and authority-omission checks.
APPLIED (§1 + §2 architecture): wa-design.css refactored to the role map under
[data-mood="ledger"] with legacy names aliased; all 12 raw hex outside the
token block removed; tests/test_design_tokens.py enforces the rule, pins the
roles, pins mood-selectability, and pins the neumorphic divergence by CSS
signature. Values unchanged — the suite is green and nothing moved visually.

**R-MOTION-SPEC (founder, 2026-07-24) — addendum to R-LANDING-2's motion
system; applies at wiring.** (1) Every animated effect on the landing and any
future surface is SPECIFIED BEFORE IMPLEMENTATION as trigger · behavior ·
duration+easing · reduced-motion fallback · tokens used (wa-design vars only —
motion introduces no new colours or shadows). design/MOTION-SPECS.md is a GATE
ARTIFACT; ux-reviewer checks implementation against it. (2) Prototyping tools
may be used to explore an effect, but production code is written in-repo
against our tokens and gated normally — we adopt patterns, not artifacts.
(3) Simplicity law restated: one designed delight per section; motion that does
not serve comprehension or the money-moment is cut at the gate.
APPLIED: design/MOTION-SPECS.md written covering shipped in-app effects (A1-A7),
the v4 unified surfaces (B1-B2) and the not-yet-built landing effects (C1-C5),
plus a cut list of rejected effects. tests/test_motion_specs.py binds the sheet
to the code so it cannot drift into fiction.

**R-LANDING-2 (founder, 2026-07-24) — RECEIVED AND RECORDED; NOT STARTED,
BLOCKED ON A MISSING PREREQUISITE.** Marketing landing rebuild, est. 2 days,
ux-gated, founder review at the end. SSR + CSS-first, vanilla JS for scroll
choreography, no framework, no WebGL library. Nine sections in narrative order:
(1) hero — bill-shock headline (R-PAINMOMENT A/B) + platform subhead "the
governance layer for your AI spend" + Start free + THE 3D MOMENT (real
dashboard screenshot in CSS 3D, tilting on pointer/scroll); (2) problem strip —
three attributed stat cards + "waste hides in shapes invoices can't show";
(3) how it works — INPUT->ANALYZE->REPORT->ACT->PREVENT ribbon as a
scroll-driven sequence, one sentence + micro-visual per stage; (4) live-feel
product tour — three real screenshots in a tabbed frame, count-ups on reveal,
labeled sample data; (5) preventive measures / governance — zero-token,
zero-trust, counts-only (FR-23 verbatim), layered validation, honest-zeros,
each linking its proof, header "We run the architecture we audit you toward";
(6) comparison strip — category-level only, no named-vendor FUD; (7) self-audit
proof — the ledger story, 32.5% with equiv-spend rail; (8) plans from the price
config + enterprise line; (9) closing CTA + trust footer. MOTION:
IntersectionObserver reveals (fade+rise 200ms), scroll-driven pipeline,
count-ups, hero tilt — all respecting prefers-reduced-motion; JS < 15KB;
Lighthouse >= 90 mobile as a GATE criterion. Gates: ux-reviewer (three-second
rule per section, claim-to-source spot check on 10 claims, banned-list scan,
Lighthouse evidence), then founder review as a stranger, on phone, before the
thread. NO-INVENTED-NUMBERS LAW extended to marketing permanently.

RECONCILED 2026-07-24 night (founder): the incident/funnel order was never
pasted; R-PREMISE-CHECK applied correctly. Its surviving requirements are
folded into the v15-ui-unify WIRING order. SEQUENCING: v4 ships as the INTERIM
(it is the seam fix and it is gated); R-LANDING-2 then DRESSES it, and the v4
landing is formally the "Part B" skeleton the ruling meant. Defect repair and
enhancement stay SEPARATE DEPLOYS. v4 sections that R-LANDING-2 replicates are
upgraded in place; the three genuinely new sections (animated pipeline, product
tour tabs, comparison strip) arrive with R-LANDING-2.
AMENDMENTS accepted from the pre-flight: (a) problem-strip third card = the 98%
FinOps figure already on file; the unsourced "#1 unmet ask" card is DROPPED
unless a citable source is added to the inventory first; (b) "We run the
architecture we audit you toward" RELEASED for landing §5; (c) Lighthouse gate
substituted until tooling exists — measured budgets as evidence (transfer
<300KB, JS <15KB, CSS <25KB, hero <120KB), verified by curl/du in the gate
report; real Lighthouse >=90 mobile preferred if installable.

UNBLOCKED (founder, 2026-07-25): the incident/funnel order is confirmed
SELF-CONTAINED and SATISFIED — its surviving requirements shipped with the
wiring milestone (login/signup CTAs, post-login → /dashboard, legacy-route
behaviour fix, no-store HTML, Terms FR-23 canonical + test, seeded hero at
95KB). Problem-strip third card = the attributed 98% FinOps figure ("#1
unmet ask" permanently dropped); "We run the architecture we audit you
toward" RELEASED for §5; the wired v4 landing is the skeleton and R-LANDING-2
dresses it IN PLACE (three new sections added: animated pipeline, product-tour
tabs, comparison strip); measured budgets ARE the gate evidence (JS<15KB,
CSS<25KB, transfer<300KB, hero<120KB via curl/du) with real Lighthouse only
if installable in-env. GO issued; chain: landing → stranger-path smoke →
unified deploy (backup first) → founder production walkthrough → thread on
founder ACCEPT.

**R-STMT-GATING (founder, 2026-07-25).** Savings Statements are ARCHIVED for
every plan, always (R-ARCHIVE-ALWAYS untouched; Free reads them in-app).
EMAIL DELIVERY is gated: Pro/Team receive the monthly statement email always;
Free receives it ONLY for months with activity (an audit ran or a finding
changed state that month) — a monthly email of zeros to a dormant Free
account is spam, but an activity statement showing identified-but-unverified
savings is the best upsell artifact. Pro blurb sells "monthly Savings
Statement, every month" honestly; the Free plan line states statements are
archived in-app and emailed when there is something to show. Tests pin
delivery gating per plan + activity and unconditional archiving. Resolves the
open question recorded at the §5 authority audit. Carried debt
(schedule.py 84.8%) ACCEPTED per the V-D10 slack rule.

ORIGINAL BLOCK (resolved, kept for the record): the ruling states it "runs AFTER the incident/funnel order completes
(that order's Part B is the skeleton this dresses)". No incident/funnel order
exists in PLAN, PLAN-V15, STATUS, BACKLOG or docs; the only recorded Part B is
docs/12-FLYWHEEL.md from the 2026-07-22 vision order, which is complete and is
not a landing skeleton. Paused and reported per R-PREMISE-CHECK rather than
executed literally. See STATUS for the open questions blocking a start.

**R-SAAS-BASICS (founder, 2026-07-26) — gap-audit corrections, items 1-3+4a
shipped.** (1) Plan SOLD as "Scale" ("5 connected sources, priority support");
the internal key stays "team" — subscription rows are data and migrations are
additive-only; every display path now goes through the catalogue (str.title()
on the key was silently resurrecting "Team"); ruled test: no rendered public
surface says Team as a plan name. Multi-user seats remain at the X-03 trigger.
(2) Contact support (mailto support@tokenops.cloud, replies within 1 business
day) in the app Help group, public footer and billing. (3) status.tokenops.cloud
linked in the footer; UptimeRobot public page + CNAME are founder-dashboard
steps recorded in the runbook (no UptimeRobot/DNS credential exists in this
system). (4a) Close account: typed-phrase explicit-confirm with every
consequence in words; executes purge (ONE definition), revokes all keys and
deletes ciphertext, cancels the subscription locally, kills the session,
audit-logs. DEVIATION, recorded: provider-side cancellation cannot be
programmatic — the payment adapters are link+webhook only, no provider API
credential exists — so the audit-log entry + daily digest carry the manual
task to the founder inside the 1-business-day promise; programmatic cancel
lands with API-key adapters (BACKLOG trigger). (5) Gap audit performed;
remaining absences DELIBERATE with triggers recorded in BACKLOG: data export
(first request or first EU enterprise review), SSO/orgs (X-03), API keys
(first integration request), PWA/native (never before repeat mobile usage in
analytics), public changelog page (docs backlog).

**R-PREMISE-CHECK (founder, 2026-07-24) — PERMANENT LAW.** An order whose
stated premise is false is PAUSED and reported, never executed literally.
Established when the v1.5 deploy order specified an incremental migration
"001->007 (rehearsed)" while production actually stood at 002, making the real
path five unrehearsed migrations over live customer data. Ratified with it:
premise-check before execution; refusing a one-command path that would have
migrated production ahead of any rehearsal gate; refusing to move customer
data off-box in order to test; rehearsing on an on-box copy of real data; and
dropping that copy the moment it had served its purpose.

**R-NULL-HONEST-ZEROS (founder, 2026-07-24) — FINAL.** Columns added to
existing rows stay NULL and read conservatively: legacy findings earn no
verified-savings credit until re-audited, legacy audits do not qualify for
verification. Honest zeros over invented savings. NO BACKFILL, EVER.

**R-CC-LINK (founder, 2026-07-23) — BACKLOG consolidation, zero v1.5/V-D10
change.** WP-SKILL and WP-COLLECTOR merge into ONE subscriber deliverable,
WP-CC-LINK: `pipx install tokenops && tokenops link <code>`, a device-link
exchange (short-lived dashboard code -> scoped revocable device token, no keys
typed). One command performs consent, skill install, collector arming and the
self-update path. LAW: one human action is the FLOOR, never zero — remote or
silent install is forbidden as a trust posture, and the consent screen is
marketed as a feature. Sources gains a "Claude Code" type at build time
(linked machines, last ship, revoke). Trigger: immediately post-v1.5 launch,
est. 2-3 days. Registered line updated per §4.

**R-ZTA (founder, 2026-07-22) — positioning; zero v1.5 scope change.**
(a) Zero-token vocabulary in launch/landing/docs engineering page:
"deterministic engine, no inference — we never burn your tokens to count
your tokens." Hightower PlatformCon 2026 attribution where referenced (one
short quote max, linked). D6 depth-(a) alias: "loop burn". (b) BACKLOG: D7
EXPORT-CANDIDATE detector (recorded, not built). (c) Build Health metrics
adopt "loop engineering" vocabulary when they ship.

**R-ARCH-PATTERNS (founder, 2026-07-22) — name what is enforced; zero scope
change.** (a) docs-site Engineering gains an "Architecture principles"
section where EVERY claim cites its test/spec id — the no-uncited-prose law
applied to our own page: ZERO-TOKEN (NFR-01 + import guard); ZERO-TRUST
across five axes (input never trusted · network never trusted · least
privilege · explicit verification · assume breach), each item linking its
FR/NFR/test; LAYERED DATA VALIDATION drawn as the five-gate ladder (ingest
validation → normalization contract → founder-verified golden pricing →
detector conservative rails → R-Q9 proving audit → statement
archive-freeze). (b) Sales line registered: "We run the architecture we
audit you toward." (c) BACKLOG: Act-stage "export this loop" playbooks per
D7 finding. (d) LAW: architecture labels are adopted only where practice
already exists or a ruling builds it — we name what we enforce; we never
enforce by naming.

**R-INTENT-DECLARED + R-INTENT-LADDER (founder, 2026-07-22) — docs/12 +
BACKLOG; zero v1.5 change.** (a) LAW: the platform NEVER infers developer
intent from CONTENT and NEVER takes optimization decisions autonomously.
Intent enters by declaration; decisions ship as recommendations only, until
a human-approved policy exists (control-plane era, X-02 path). FR-22 and
NFR-01 are the structural reasons. (b) THE LADDER — intent is read at three
levels: BEHAVIORAL (deterministic shape algorithms over counts/timing/
models/cache fields — the detector suite incl. D7: recurring shapes =
loops, monotonic prompt growth = context bloat, burst patterns = retries/
flail, repeat-prefix-no-cache-reads = unclaimed caching); DECLARED (task
tags: class, quality sensitivity, expected recurrence); LEARNED (L0
Applied/Dismissed labels → L2 threshold training). Only CONTENT-inferred
intent is forbidden. Sales language: "your traffic's shape tells us what
it's doing — you tell us why — we never read what it says." (c) BACKLOG:
TASK DECLARATION layer (optional route/tag purpose declarations, consumed
by detectors; counts-safe metadata, FR-22 untouched). (d) COPY LAW for
depth (c): findings address the developer as the operator being handed
efficiency wins, never the party at fault — "your pipeline, same output,
lower bill." Owner depth stays money-verified. ux-reviewer checks tone at
both depths.

**R-PAINMOMENT (founder, 2026-07-20) — GTM targeting addendum.** Launch
outreach targets TRIGGER MOMENTS, not cold personas: (a) X/Reddit/HN posts
complaining about OpenAI/Anthropic/Claude Code bills — search-and-reply
with the free audit, not broadcast; (b) model-release weeks (cost profiles
shift — audit demand spikes); (c) the thread's hook leads with the
bill-shock scenario, not the category. Landing hero line test at polish:
"Just got an AI bill you can't explain?" variant vs current. No product
change. [Applied: Asset 1 hook rewritten + distribution section added to
launch/launch-assets-DRAFT.md; hero test lands in v1.5 WP-7 (GRAND ORDER
v2 delivers R-LAUNCH-POLISH there).]

**GRAND CONSOLIDATED ORDER v2 (founder, 2026-07-20, FINAL).** Supersedes
and DELIVERS pending R-LAUNCH-POLISH + R-ONBOARD (inside v1.5 WP-7).
Part A: platform vision recorded verbatim at §0.0. Part B: intelligence
flywheel recorded at docs/12-FLYWHEEL.md (tiers T1-T5 on one frame
contract with per-tier honest detector coverage; LLM-free engine as label
factory; learning ladder L0-L4 under the HONESTY LAW — no model ships
below its data threshold, every output prints training-population size;
four moats verbatim; R-STANDARDS: OTel GenAI semconv T4 constraint +
FOCUS-aligned export recorded now, spec'd at T4 build; docs-site Standards
page added). Part C: all three follow-ups were already applied 2026-07-20
(commit 82024a1) — verified, not redone; digest-arrival confirmation
pending founder inbox. Part D: v1.5 "MONITOR" SCOPE FROZEN — 14 working
days, WP-1 Connect (primary onboarding, executes promoted R-CONNECT),
WP-2 dashboard + R-OWNER-LENS (owner view PRIMARY: verified-savings
headline from L0 deltas, spend/waste trends, top findings by $, sources
status, next-audit countdown; engineering tab SECONDARY; FR-31 folded in),
WP-3 proactive re-audits + alerts (observe-and-alert ONLY — X-02
enforcement forbidden) + L0 feedback capture (mandatory), WP-4 Savings
Statement (monthly CFO-forwardable; deltas verified, estimates labeled),
WP-5 settings, WP-6 subscriptions (Razorpay + Stripe; Free 1 one-shot /
Pro $99/mo 1 source / Team $299/mo 5 sources / one-shot $500 kept; FR-27
dedup rails; dunning), WP-7 polish + onboard (landing visual pass, hero =
dashboard + sample-report screenshots, /sample FR-16, guided get-your-logs
tabs with counts-only reassurance, report web visual pass, owner-aimed
copy, hero A/B per R-PAINMOMENT, pricing framed against the Savings
Statement; ux-reviewer gates every changed surface). X-05 relaxed ONLY to
SSR + htmx (docs/01 §G amendment); FR-22 extended to connector/streamed
data; FR-31 added. LAWS unchanged (vv + cold-reviewer per milestone group,
spec-guard traceability, golden discipline, TE incl. TE-11, K-2). HARD
CONDITIONS: (a) scope frozen — additions = one BACKLOG line; (b) day 14
ships whatever exists; (c) founder walkthrough of the CURRENT live product
during the build; (d) at completion: launch-asset refresh (figure
inventory only, rails attached), public thread posts, day-45 revenue gate
restarts from that launch date. FIRST TASK then STOP: PLAN-V15.md
(day-by-day WPs, test IDs, gate schedule, numbered ambiguities); no
application code until founder approves PLAN-V15.

### 0.2 Standing decisions

**PY-VERSION: Python 3.14** (kickoff permits 3.14 if pandas/pyarrow/weasyprint/psycopg
install cleanly). Verified 2026-07-17 on linux x86_64 with uv 0.11.18:

- `uv pip compile --python-version 3.14 --only-binary :all:` over the full kickoff
  dependency list resolves with wheels only (exit 0). 3.13 also resolves (fallback).
- Real install + import test on CPython 3.14.5: pandas **3.0.3**, pyarrow **25.0.0**,
  psycopg **3.3.4** (binary), weasyprint **69.0** — all OK.
- Docker base: `python:3.14-slim` + weasyprint system libs (pango/harfbuzz/gdk-pixbuf).
- Note: pandas 3.0 is a major version (copy-on-write default, string dtype). Greenfield
  code, so no migration burden; detectors written against 3.0 semantics from day one.

**GIT-FLOW** (updated for R-Q1): repo is not yet a git repo → `git init` is the first
D1 action. One branch per **gate group** (`d1-scaffold`, `d2-d3-ingest-pricing`,
`d4-d5-detectors`, `d6-d7-runner-report`, `d8-d9-auth-payments`, `d10-lifecycle`,
`d11-d12-uat`, `d13-deploy`, `d14-launch`). Gate agents receive `git diff main...HEAD`
(the group diff, written to a file), STATUS.md, and only their charter-named docs.
Merge to main after all scheduled gates PASS; tag `dN` at each milestone completion.
Each Dn still ends all-green (tests) before Dn+1 starts, per CLAUDE.md rule 6.
Conventional commits throughout.

**PAYMENT-SDKS: none.** Razorpay/Stripe webhook signatures are HMAC-SHA256 — verified
with stdlib `hmac`/`hashlib`. Payment links are static env-configured URLs. Keeps
dependency list exactly as the kickoff specifies; no third-party payment SDKs.

**CRON: ofelia sidecar** in docker-compose (runbook §1 allows "ofelia or host crontab").
Keeps deploy a single `docker compose up -d`, staging identical to prod. Jobs: purge
02:00 UTC, backup 02:30 UTC, daily digest (wired at D10).

**MAIL: port + log adapter default.** `MailPort` with a structured-log adapter when
SMTP_* unset (dev prints magic link / report link to logs); SMTP adapter env-gated
(FR-20). Runner (D6) depends only on the port, so mail order-of-build is not blocking.

**COVERAGE GATE mechanics**: pytest-cov can't express "85% on services/*, 100% on
coster.py + findings.py" in one flag → small `scripts/coverage_gate.py` parses
`coverage json` and enforces both thresholds (paths that don't exist yet are skipped,
so the gate is green at D1 and tightens automatically as packages appear).

**MYPY scope**: strict on `src/tokenops_cost_auditor/services/*` per docs/05 §4; standard elsewhere.

---

## 1. Work packages

Each WP lists: files to create, tests (IDs from docs/05-TEST-PLAN.md §3), and the gate
sweep that covers it (§2, per ruling R-Q1). Universal exit criteria for every Dn: suite
green locally + CI, docs/04-TRACEABILITY.md updated in the same commit as each
implemented requirement, STATUS.md paragraph written, context cleared per TE-9 before
Dn+1; the group's gate sweep must PASS before the group branch merges to main.

### WP-D1 — Scaffold from scratch

Goal: uv project, src layout per docs/03-LLD.md §1, compose stack, CI green, rules files.

Files:
- `pyproject.toml` (deps exactly per kickoff; ruff + mypy config; requires-python ">=3.14"),
  `uv.lock`, `.python-version`, `.gitignore`
- `CLAUDE.md` — ONLY the 7 kickoff items; TE-1..TE-10 + K-1..K-4 copied verbatim from
  docs/10 §2 and §5
- `STATUS.md` (TE-4 shared memory, one paragraph per milestone), `BACKLOG.md` (empty —
  scope-freeze parking lot)
- `src/tokenops_cost_auditor/__init__.py`, `config.py` (pydantic-settings; every var in docs/03 §7),
  `main.py` (app factory, request-id middleware, `/healthz` with db + disk_free checks)
- `src/tokenops_cost_auditor/obs/{logging.py,errors.py,ratelimit.py}` (structlog JSON, env-gated
  Sentry hook, slowapi limiter instance)
- Package skeleton (`__init__.py` only, no stub logic): `web/`, `api/`, `services/`
  (+ `ingest/ pricing/ rules/ report/ lifecycle/ payments/ mail/`), `persistence/`
- `src/tokenops_cost_auditor/persistence/models.py` (DeclarativeBase only), alembic init
  (`alembic.ini`, `persistence/migrations/`) — no tables yet, additive-only policy noted
- `Dockerfile` (multi-stage uv build on python:3.14-slim + weasyprint system libs),
  `docker-compose.yml` (caddy→app→postgres:17 + ofelia; postgres compose-internal only;
  volumes pgdata/uploads/reports/backups; json-file logging max-size 50m, max-file 5),
  `Caddyfile`, `.env.example` (every config.py var, secrets blank)
- `.github/workflows/ci.yml`: lint(ruff) → type(mypy) → tests(postgres:17 service) →
  coverage gate → build image; perf job schedule-gated (nightly only); manual deploy stub
- `scripts/coverage_gate.py`
- `tests/conftest.py`, `tests/test_smoke.py`

Tests: T-OBS-01..03 (request-id in log lines; /healthz degrades when DB down; Sentry hook
called on unhandled error, mocked). These are the "empty suite" that makes CI green.
Gates: **ops-engineer, spec-guard**.
Extra exit criteria: `docker compose config` valid; image builds in CI; no secrets in repo.

### WP-D2 — Ingest

Files:
- `services/ingest/{base.py,openai_jsonl.py,anthropic_jsonl.py,generic_csv.py,
  normalizer.py,validator.py}` — LogParser protocol + `detect_format()`; normalize to
  CallRecordFrame per docs/03 §2 (UTC coercion, raw_extra preserved, prefix_hash per
  ADR-7 when text present — hash computed in-memory, text never retained);
  validator emits per-row error file, aborts <95% valid (FR-03)
- Fixtures: `tests/fixtures/{openai_small.jsonl,anthropic_small.jsonl,mixed_dirty.jsonl,
  generic.csv}` (F1–F4) + generator script `tests/fixtures/gen_fixtures.py` (seeded RNG)
- Generic-CSV column contract documented in `generic_csv.py` module docstring (surfaced
  to customers via export docs at D12)
- R-ICP addition: `scripts/exporters/claude_code_export.py` (documented Claude Code
  local-log → TokenOps JSONL exporter, FR-24) + session-log fixture + tests T-EXP-01..02;
  traceability row added in the same commit

Tests: T-ING-01..04 (format detection, oversize reject, wrong extension, empty file),
T-ING-05..07 (column mapping per provider, raw_extra, UTC), T-ING-08..09 (dirty fixture
row-error file; <95% aborts).
Gates: none at D2 — covered by sweep **G2** at end of D3.

### WP-D3 — Pricing

Files:
- `services/pricing/{table.py,coster.py}`, `services/pricing/data/prices.yaml`
  (versioned; provider × model × {input, output, cached} with effective_from ranges)
- `tests/fixtures/pricing_golden.csv` — hand-computed spreadsheet (founder-verifiable;
  money-math commit discipline starts here: golden update + spreadsheet diff in commit msg)
- PricingGapError path: unknown model → audit continues, "unpriced models" listed (docs/03 §8)

Tests: T-PRC-01..03 (rate lookup, effective-date boundaries, unknown-model path),
T-PRC-04 (per-call golden values), T-PRC-05 (hypothesis property: sum of parts
reconciles ±0.5%, NFR-07).
Gates: sweep **G2** (vv-engineer, cold-reviewer) covering D2-D3 — golden spreadsheet
founder-verified BEFORE the sweep runs (R-Q3). Pricing schema: four rates per R-Q4.

### WP-D4 — Rules engine part 1 (highest-signal detectors)

Files:
- `services/rules/{base.py,findings.py,registry.py}` — Detector protocol, Finding
  dataclass + estimator helpers (FR-13; EvidenceRef ≤20, counts/hashes only — FR-22),
  ordered registry with enable flags
- `services/rules/d2_missing_cache.py`, `services/rules/d4_retry_storm.py` (docs/03 §3)
- Fixtures: `waste_pack.jsonl` v1 (D2+D4 traffic with KNOWN golden savings),
  `clean_optimal.jsonl` (F6, zero-findings guard) + generator additions

Tests: T-RUL-00 (registry order stable, disable flag), T-RUL-EV-01 (evidence ≤20, no
text fields — FR-22 at test level), T-RUL-D2-01..03, T-RUL-D4-01..02 (each: exact golden
on waste_pack / silent on clean_optimal / threshold boundary). D2 savings formula and
cacheable_tokens per R-Q4/R-Q5.
Gates: none at D4 — covered by sweep **G3** at end of D5.

### WP-D5 — Rules engine part 2 (complete detector set)

Files:
- `services/rules/{d1_oversized_model.py,d3_prompt_bloat.py,d5_unbounded_max_tokens.py,
  d6_chatty_loop.py}`; frontier-model list + suggested-model mapping in config
- `waste_pack.jsonl` v2 — all six detectors fire with golden numbers complete
- `tests/test_import_guard.py` — T-NFR-01: no anthropic/openai/httpx/requests inside
  services/rules and services/pricing (static AST/grep check)

Tests: T-RUL-D1-01..03, T-RUL-D3-01..02, T-RUL-D5-01..02, T-RUL-D6-01..03, T-NFR-01.
Gates: sweep **G3** (vv-engineer, spec-guard, cold-reviewer) covering D4-D5.

### WP-D6 — Runner end-to-end, aggregates, report JSON, status API

Files:
- `services/runner.py` — AuditRunner per docs/03 §4 (status transitions, failure path,
  idempotent re-run); wired via FastAPI BackgroundTasks (NFR-10, ADR-5)
- `services/report/{model.py,render_json.py}` — ReportModel assembled from engine
  outputs, render layer does NOT recompute money math
- `services/lifecycle/auditlog.py` (append-only writer; runner logs audit.completed)
- `services/mail/base.py` + log adapter (port only; SMTP at D8)
- `persistence/models.py` (users, audits, findings, call_aggregates, audit_log),
  `persistence/repo.py`, migration `001_initial`
- `api/routes_upload.py` — POST /api/v1/audits (FR-25 prefix; auth+paid enforcement
  stubs behind interfaces until D8/D9; 200MB cap, content sniff, rate-limited with
  NFR-12 user-else-IP keying + Retry-After), GET /api/v1/audits/{id}/status with
  queue position (NFR-13 MAX_CONCURRENT_AUDITS admission); FR-26 Idempotency-Key
  handling (persisted keys, 201/200 replay semantics); NFR-14 error envelope on
  every /api/v1 handler

Tests: T-API-01..02 (upload happy path; queued→processing→done), T-API-03 (/api/v1
mounting), T-API-04..05 (idempotency 201/200 replay), T-API-06 (concurrency cap +
queue position), T-API-07 (error envelope), T-NFR-12 (user-else-IP + Retry-After),
T-REP-01 (ReportModel numbers == engine numbers), T-REP-03 (JSON schema validated),
T-LIF-04 (aggregates counts only), T-NFR-03 (burst upload → 429), T-NFR-11 (UTC
everywhere, USD internal).
L2 integration: AuditRunner on F1/F5 against real Postgres (CI service).
Gates: none at D6 — covered by sweep **G4** at end of D7 (R-Q1 nuance: UML emitted there).

### WP-D7 — PDF + web report + signer + CLI

Files:
- `services/report/{render_pdf.py,signer.py}` (weasyprint on templates/pdf/report.html;
  itsdangerous signed expiring URLs)
- `web/templates/{base.html,report.html,pdf/report.html}` + print CSS — exec summary
  (spend, optimized projection, savings %), charts (by model, by day), savings waterfall,
  findings ranked by monthly $ impact, methodology appendix, data-handling statement.
  Methodology appendix MUST include the R-GOLDEN-C3 floors note: v1 excludes OpenAI
  long-context surcharge and regional data-residency multipliers → spend estimates
  are conservative floors
- `web/` report route GET /r/{signed} (FR-15)
- `cli.py` — `tokenops-cost-auditor audit file.jsonl --out report.pdf` (FR-04)
- Stretch (S): synthetic redacted sample report fixture (FR-16, T-REP-07)

Tests: T-REP-02 (PDF non-empty, savings % present), T-REP-04 (methodology appendix
incl. R-GOLDEN-C3 floors + haircut disclosures), T-REP-08 (FR-28 pricing version +
unpriced models in JSON + PDF),
T-REP-05..06 (signed URL valid/expired/tampered), T-CLI-01, T-REP-07 (S, stretch).
Gates: sweep **G4** (architect — emits docs/uml/*.mmd, vv-engineer, ux-reviewer)
covering D6-D7.

---

## 2. Gate schedule per gate group (resolved per founder ruling R-Q1/Q2)

Grouped rows gate ONCE, at the end of the group. Order within a sweep as listed. Every
gate receives: the group diff (`git diff main...HEAD` written to a file), STATUS.md, its
charter-named docs only. FAIL → fix in main thread → re-run that gate on the new diff
only (TE-10). Never per-prompt, never per-file. No gate spawns another agent (K-4).

| Gate sweep | Fires at end of | Gates (in order) | Notes |
|------------|-----------------|------------------|-------|
| G1 | D1  | ops-engineer, spec-guard | scaffold conformance |
| G2 | D3 (covers D2-D3) | vv-engineer, cold-reviewer | golden spreadsheet founder-verified first (R-Q3) |
| G3 | D5 (covers D4-D5) | vv-engineer, spec-guard, cold-reviewer | T-NFR-01 in force |
| G4 | D7 (covers D6-D7) | architect, vv-engineer, ux-reviewer | architect emits docs/uml/*.mmd here (D6 content — see R-Q1 nuance) |
| G5 | D9 (covers D8-D9) | ux-reviewer, cold-reviewer, spec-guard | ux window D7–D9 |
| G6 | D10 | ops-engineer, vv-engineer | outline |
| G7 | D12 (covers D11-D12) | vv-engineer (UAT evidence + perf) | outline |
| G8 | D13 | ops-engineer + architect (D13 UML refresh only) | outline |
| G9 | D14 | spec-guard (final traceability sweep) | outline |

---

## 3. D8–D14 outline (coarse; detailed packaging appended to PLAN.md at end of D7)

- **D8** Auth + landing: `web/` auth routes (magic link signed 15-min single-use,
  session cookie HttpOnly/Secure/Lax), `mail/smtp.py`, templates landing (PRD §4 copy,
  FR-23 verbatim policy string) + ToS/Privacy/DPA-lite. Tests T-AUTH-01..04, T-WEB-01,
  T-MAIL-01(S). Copy angles (founder-approved 2026-07-17): lead with the agent-fleet
  story (R-ICP); differentiation line vs auto-routers (Copilot Auto etc.): "routers
  pick a model; we find the other five kinds of waste — and prove it in dollars"
  (routing addresses only D1; D2-D6 waste classes are untouched by routers).
- **D9** Payments + admin: `payments/{base,razorpay_link,stripe_link}.py`,
  `api/routes_webhooks.py` (HMAC verify + FR-27 timestamp tolerance 5 min +
  processed-event-id dedup, append-only table), `web/` admin (X-Admin-Token),
  migration 002 (payments + webhook_events). Tests T-PAY-01..07, T-ADM-01..04.
- **D10** Lifecycle + ops: `lifecycle/purge.py`, ofelia job wiring, `scripts/backup.sh`,
  `scripts/daily_digest.py` (incl. NFR-15 pricing-age + FR-29 failure surfacing),
  `scripts/pricing_refresh.py` (FR-29, read-only diff; T-OPS-04). Tests T-LIF-01..03;
  manual drills T-OPS-01..02 logged.
- **D11** UAT-1 dogfood (founder's Claude Code logs); findings-quality fixes.
- **D12** UAT-2 external audit; export docs hardened; T-PERF-01 (1M fixture, NFR-04).
- **D13** Production deploy per runbook §2; smoke; UptimeRobot; T-OPS-03.
- **D14** Launch; spec-guard final sweep.

Test-ID completeness: every M-priority ID in docs/05 §3 is owned above —
D1: T-OBS-01..03 · D2: T-ING-01..09 · D3: T-PRC-01..05 · D4: T-RUL-00/EV-01/D2/D4 ·
D5: T-RUL-D1/D3/D5/D6, T-NFR-01 · D6: T-API-01..02, T-REP-01/03, T-LIF-04, T-NFR-03,
T-NFR-11 · D7: T-REP-02/04/05/06, T-CLI-01 · D8: T-AUTH-01..04, T-WEB-01 ·
D9: T-PAY-01..05, T-ADM-01..04 · D10: T-LIF-01..03 · D12: T-PERF-01 ·
manual: T-OPS-01..03. S-priority: T-REP-07 (D7 stretch), T-MAIL-01 (D8).

---

## 4. Spec ambiguities — numbered questions (RESOLVED)

All twelve questions were ruled by the founder on 2026-07-17 — rulings are binding and
recorded in §0.1. Original questions kept below for the record; where a ruling overrode
a proposal (Q1, Q4, Q5), §0.1 wins.

1. **Gate cadence for grouped rows.** docs/10 §3 groups milestones ("D2-D3", "D4-D5",
   "D8-D9"). TE-1 says gates run at the end of *each* Dn. **Proposal:** run the row's
   gates at the end of each milestone in the range (as in §2 table above).
2. **ux-reviewer / architect window conflicts.** docs/10 §1 says ux-reviewer "D7-D8
   only"; §3 schedule includes it in the D8-D9 row; its charter says D7-D9. Also the
   architect charter emits UML at D13, but the §3 D13 row lists only ops-engineer.
   **Proposal:** §3 schedule wins → ux-reviewer at D7, D8, D9; architect additionally
   runs at D13 solely to refresh docs/uml/ per its charter.
3. **prices.yaml seed + golden spreadsheet.** I will draft OpenAI + Anthropic rates from
   provider public price pages at D3 and hand-compute fixtures/pricing_golden.csv.
   **Proposal:** founder verifies the golden spreadsheet numbers before the D3 gate runs
   (money math is the product; a wrong seed table poisons every golden test downstream).
   Same review covers the D1-detector frontier list + suggested-model map at D5.
4. **Anthropic cache accounting.** Anthropic logs split cache_creation vs cache_read
   tokens; CallRecord has a single `cached_tokens` and FR-05 pricing has one `cached`
   rate. **Proposal:** `cached_tokens` = cache_READ tokens; add an optional
   `cache_write` rate per model in prices.yaml (used when present, else write tokens
   billed at input rate — conservative). Documented in methodology appendix.
5. **D2 missing-cache `delta_est` undefined** (docs/03 §3). **Proposal:** hash-based
   buckets → delta_est = 0 over the hashed prefix length (exact, confidence=conservative);
   token-count-heuristic buckets → configurable `CACHE_SUFFIX_EST_TOKENS` default 200
   subtracted from prompt_tokens, confidence=estimated.
6. **prefix_hash N** (ADR-7 "first N tokens' text"; no tokenizer in the dependency
   list). **Proposal:** SHA-256 over first `PREFIX_HASH_CHARS=4096` characters
   (≈1024 tokens at ~4 chars/token) when text present in logs.
7. **Monthly extrapolation rule.** Findings report monthly_cost_impact_usd but uploads
   cover arbitrary windows. **Proposal:** scale observed waste by `30 / observed_days`
   (observed_days = span of distinct UTC days in the frame, min 1); stated in the
   methodology appendix; no scaling cap (conservative estimators already applied).
8. **Payment ↔ audit entitlement.** FR-18 "payment before upload unlock".
   **Proposal:** one completed payment = one audit credit; free-for-testimonial audits
   = admin mark-paid with amount 0, `paid_via='comp'` (audit-logged).
9. **Signed report URL expiry** (FR-15 "expiring", duration unspecified).
   **Proposal:** `REPORT_URL_EXPIRY_DAYS=30` (config); report artifacts persist after
   the 7-day raw purge; admin can re-issue links (FR-19 download).
10. **D3 prompt-bloat "similar completion sizes"** grouping undefined. **Proposal:**
    log2 buckets on completion_tokens; route p90 prompt_tokens compared to corpus
    median within the same bucket; flag when > BLOAT_MULT (2.0) ×.
11. **Session lifetime** unspecified (magic link expiry is 15 min, session isn't).
    **Proposal:** `SESSION_TTL_DAYS=7`, sliding not renewed (simple, v1).
12. **Cron mechanism.** Runbook allows ofelia or host crontab. **Proposal:** ofelia
    sidecar in compose (single-command deploy, staging=prod parity).

---

## 5. Token-economy compliance notes (self-applied)

Context at PLAN.md authoring: ~60K tokens (docs read once, whole — mandated by kickoff;
everything else grep/targeted). Milestone hygiene per TE-9/K-3: clear at each Dn start,
carry only PLAN.md + STATUS.md + current Dn section. K-2 in force: two failed fix
attempts on one test → STOP, write state to STATUS.md, ask founder.
