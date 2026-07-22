# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

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
nav. OPEN: PLAN-FLYWHEEL §6 rulings R-F1 (training vs promise — still the
blocker for Tracks A/B), Q6 (C3 saved views + export), Q4/Q5/Q7/Q8.

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
