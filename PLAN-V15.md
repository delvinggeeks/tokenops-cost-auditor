# PLAN-V15.md — v1.5 "MONITOR" build plan (GRAND CONSOLIDATED ORDER v2, Part D)

Status: **APPROVED by founder 2026-07-20, with rulings recorded in §0.**
Scope: FROZEN by GRAND ORDER v2 (founder, 2026-07-20). 14 working days.
Governing docs: docs/00-07, 09, 10, 12; PLAN.md §0.0-0.1 (vision + order).
Author: Lokesh Prasanna Kumar S. Date: 2026-07-20.

## 0. Decisions of record (founder rulings at approval, 2026-07-20)

**R-Q1 — T2 reduced detector set.** ACTIVE on T2: D1 (aggregate variant:
model-mix vs avg completion size per bucket), D2 (via the providers'
cached-token fields), D3 (aggregate prompt-size averages, coarse —
confidence=estimated). INACTIVE on T2: D4, D5, D6 — each appears in T2
reports as a labeled "requires per-request logs" row with a one-line
upgrade path to upload/collector (honest coverage per docs/12, and a
built-in upsell). NEVER emit a savings number from a detector the tier
cannot support. New aggregate estimators are money math: golden files +
spreadsheet derivation in the NOTES sheet, same commit (CLAUDE.md rule 4).

**R-Q5/Q6 — plan source accounting.** A "source" = one active provider
org connection. Free = 1 one-shot FILE audit only (no connections, no
scheduler, no card required). Pro = 1 connected source + weekly scheduled
audits + unlimited manual file uploads (fair-use note in ToS). Team = 5
connected sources. Swapping = revoke + connect (active-connection count
is what is limited). Downgrade below current source count: extra sources
auto-paused oldest-first, never deleted.

**R-Q9 — VERIFIED headline formula (money math; golden discipline).**
verified_savings(month) = Σ over findings with status=Applied of
max(0, baseline_monthly_impact − recomputed_impact_same_detector_and_route),
counted ONLY after ≥1 post-application audit covering ≥7 days of data;
per-finding verified amount capped at its original estimate. Manual
savings-realized entries are shown separately, labeled
"customer-reported", NEVER in the verified headline. Unapplied findings
appear as "identified", never as savings. Spreadsheet derivation for the
formula's fixture in the NOTES sheet.

**R-Q11/Q12 — payments routing + dunning.** Razorpay for India-billing
customers (INR price list FIXED IN CONFIG: Pro ₹8,999/mo, Team ₹26,999/mo
— display both); Stripe for everyone else (USD). One subscription per
account; currency chosen at checkout by billing country. Dunning: day 0 =
email + provider smart retries; day 7 = account read-only (dashboard
visible, scheduled audits paused, connections kept); day 21 =
subscription cancelled, account reverts to Free; data lifecycle unchanged
(normal purge rules — cancellation never triggers extra deletion).

**R-WALKTHROUGH.** Day-3 slot ACCEPTED as scheduled — founder held to it;
the walkthrough punch list becomes fix items inside this build, never new
scope.

**Remaining questions (Q2,3,4,7,8,10,13,14,15,17,18 + unruled parts of
Q11).** Defaults accepted under two standing guardrails: any default
touching money math is recorded in the golden NOTES sheet with rationale;
any default interacting with X-scope, FR-22, or the honesty law is
ESCALATED, never defaulted. Chosen defaults are listed in STATUS at the
end of M1.

**R-DESIGN + R-DESIGN-ADDENDUM (founder, 2026-07-20; full text PLAN
§0.1).** Binding on WP-2/WP-7 and all future surfaces: auditor's
aesthetic + precision-luxury elevation, one wa-design.css token sheet,
three-second rule as ux acceptance, workflow specs a-i, motion system
with number moments, WP-2 starts with static mockups (dashboard +
finding card + first-run) gated by ux-reviewer BEFORE wiring. G-V1 stop
deliverables amended to include the mockup set for founder
three-second-rule review. Zero scope/date change.

Laws in force, unchanged: TE-1..TE-11 token economy; K-1..K-4 kill switches;
golden money-math discipline (engine untouched — byte-identical goldens are a
standing regression gate); FR-22 counts-only at every tier's door; X-05
relaxed ONLY to SSR + htmx partials (vendored asset, no CDN, no build step);
X-01/X-02 stand — v1.5 alerts observe-and-alert only. Conventional commits;
Dn all-green before Dn+1.

## 1. Day-by-day work packages

### V-D1 (day 1) — Foundations [enables WP-1/2/3/5/6]
Additive migrations: `sources` (type, credentials_encrypted, status,
schedule, last_pull_at), `finding_feedback` (L0: audit_id, finding_id,
verdict Applied/Dismissed/Not-relevant, savings_realized_usd nullable,
actor, ts), `alert_rules` + `alert_events`, `subscriptions` (provider,
plan, status, external_ids), `statements` archive. Key-encryption module:
HKDF(SECRET_KEY, context="source-credentials") → Fernet; decrypt only in
the pull path; repr/log-guard test. Config + .env.example additions.
Tests: T-V15-MIG-01 (additive-only), T-KEY-01 (roundtrip), T-KEY-02
(revoke deletes ciphertext), T-KEY-03 (key never in logs/repr — grep
guard), env-completeness update.

### V-D2 (days 2-3) — WP-1 CONNECT (T2 ACCOUNT tier)
New `services/connectors/` package (network imports live HERE; the
T-NFR-01 import guard on rules/pricing is untouched and re-asserted).
OpenAI + Anthropic official Usage/Admin API clients, fixture-driven tests
(no live calls in CI). Pulls land as AggregateFrame with provenance +
dedup stats per row (docs/12 Stage-1 contract); reduced detector set runs
and the report states per-tier coverage honestly (which detectors could
not run and why). Connect/revoke UI (SSR + htmx): paste key → validate →
scheduled daily pull; revoke in settings stops pulls and deletes
ciphertext. Upload + CLI unchanged.
Tests: T-CON-01 (OpenAI fixture → frame), T-CON-02 (Anthropic fixture →
frame), T-CON-03 (provenance + dedup stats present per row), T-CON-04
(coverage labeling in report JSON), T-CON-05 (revoke stops pull + deletes
credentials), T-CON-06 (no text fields persisted — FR-22 tier test),
T-NFR-01 re-run.
**Day 3: FOUNDER WALKTHROUGH of the CURRENT live product (hard condition
c) — proposed slot; confirm in Q16.**

### V-D3 (day 4) — WP-3a Scheduler
Ofelia tick job → in-app due-work runner (deterministic, testable):
daily pull per source; weekly auto-audit per source; FR-26 idempotency
keys on scheduled runs (no double audits on tick overlap/restart).
Tests: T-SCH-01 (due computation), T-SCH-02 (idempotent tick), T-SCH-03
(per-source cadence).

### GATE G-V1 (end day 4) — vv-engineer + cold-reviewer + spec-guard
Diff: V-D1..V-D3. Spec focus: FR-22 tier extension, FR-26 reuse, X-scope.

### V-D4 (days 5-6) — WP-2 DASHBOARD (R-OWNER-LENS + FR-31)
/dashboard after login, SSR + htmx. PRIMARY owner view: headline "saved
this month (VERIFIED)" from L0 deltas (zero-state: MEASUREMENT-PENDING
register, never invented numbers); spend trend 30/90d; waste % trend;
top findings by $; sources status; next-audit countdown. SECONDARY
engineering tab: findings-by-detector over time. Chart machinery reused
from report rendering. FR-31 "My audits" history folded in (purged rows
metadata-only).
Tests: T-DASH-01 (owner headline math = documented delta formula),
T-DASH-02 (trends from fixtures), T-DASH-03 (auth scoping — no
cross-user leakage), T-DASH-04 (FR-31 purged-row metadata-only),
T-DASH-05 (zero-state honesty).

### V-D4g (+1 day, R-DESIGN-V3 §2; founder-accepted scope addition) — In-product guidance
Guided tour (5 spotlight steps, vanilla JS + CSS, server-persisted
dismiss, replayable), per-widget "?" help popovers, HELP sidebar group
with 4 one-screen Guide pages, workflow breadcrumbs. Help content lives
ONCE in a YAML registry rendered SSR — docs-site and popovers read the
same source and cannot drift.
Tests: T-HELP-01 (registry renders every widget's help; missing key =
test failure), T-HELP-02 (tour dismiss persists per user + replay
resets), T-HELP-03 (docs/popover parity — same registry keys).

### V-D5 (day 7) — WP-3b Alerts + L0 feedback capture (mandatory)
Alert rules: spend spike DoD, waste % above target, new HIGH finding,
soft budget crossed (observe-and-alert ONLY — X-02 test asserts no
enforcement code path exists). Email delivery on existing mail adapter.
L0 capture: Applied/Dismissed/Not-relevant per finding + optional
savings-realized; next audit auto-computes before/after deltas. Delta
formula gets a golden-style derivation row in pricing_golden_NOTES.md
(money-adjacent law).
Tests: T-ALR-01..04 (one per rule, incl. threshold edge), T-ALR-05
(observe-only guard), T-FB-01 (capture + idempotent re-vote), T-FB-02
(delta computation golden), T-FB-03 (savings-realized flows to headline).

### V-D6 (day 8) — WP-4 SAVINGS STATEMENT
Monthly one-page CFO-forwardable email: spend, waste found, fixes
applied, savings VERIFIED (deltas; estimates labeled as estimates —
verbatim register mirrors report rails). Archived to `statements`;
resend from settings.
Tests: T-STMT-01 (arithmetic golden vs hand derivation), T-STMT-02
(verified vs estimate labeling), T-STMT-03 (archive + resend idempotent).

### GATE G-V2 (end day 8) — vv + cold-reviewer + spec-guard + ux-reviewer + architect
ux scope: dashboard + statement surfaces. architect scope: connectors/
dashboard package boundaries vs docs/03 (UML emission per R-Q1 pattern).

### V-D7 (day 9) — WP-5 SETTINGS
Profile; sources add/revoke; alert thresholds; email prefs; data
controls (purge now — reuses FR-21 path with audit_log entry); billing
portal link.
Tests: T-SET-01 (threshold persistence + validation), T-SET-02
(purge-now = FR-21 semantics), T-SET-03 (revoke flow e2e).

### V-D8 (days 10-11) — WP-6 SUBSCRIPTIONS
Razorpay + Stripe subscription mode on FR-27 dedup rails. Plans: Free =
1 one-shot audit · Pro $99/mo = 1 source, weekly audits, dashboard,
alerts, statement · Team $299/mo = 5 sources + priority · one-shot $500
kept for enterprises. Webhook lifecycle (created/renewed/failed/
cancelled); plan gating middleware; dunning email on failure.
Tests: T-SUB-01 (webhook dedup/replay — FR-27 rails), T-SUB-02 (plan
transitions incl. downgrade), T-SUB-03 (gating: source counts + audit
cadence per plan), T-SUB-04 (dunning trigger), T-SUB-05 (one-shot $500
path unchanged — regression).

### GATE G-V3 (end day 11) — vv + cold-reviewer + spec-guard + ops-engineer
ops scope: webhook endpoints, scheduler jobs, secrets (no key material in
logs/backups), compose/ofelia deltas.

### V-D9 (days 12-13) — WP-7 POLISH + ONBOARD (delivers R-LAUNCH-POLISH + R-ONBOARD)
Landing visual pass with real design weight — hero = dashboard +
sample-report screenshots; /sample serves the FR-16 synthetic report;
/upload becomes guided "Get your logs" flow (tabs: Connect / Claude Code
exporter / OpenAI / Anthropic / CSV; counts-only reassurance per tab);
report web page gets the PDF's visual pass; copy re-aimed at the owner's
question; hero A/B "Just got an AI bill you can't explain?" per
R-PAINMOMENT (extended from thread to landing); pricing page frames Pro
against the Savings Statement.
Tests: T-POL-01 (FR-23 string survives verbatim, contiguous), T-POL-02
(/sample serves synthetic fixture — no real data), T-POL-03 (tab copy
carries counts-only line), figure-inventory grep (launch rails).
**ux-reviewer gates EVERY changed surface (runs day 13).**

### V-D10 (day 14) — HARDEN + SHIP (ships whatever exists — hard condition b)
Full suite exit-code-verified; goldens byte-identical; deploy via
provision.sh at tag v1.5.0; VPS smoke; launch-asset refresh (figure
inventory only, rails attached; Connect NOW claimable — it ships in this
build); founder approval → public thread posts → day-45 revenue gate
restarts from that date.
Final gates: spec-guard FINAL SWEEP + vv full + ops-engineer deploy check.

## 2. Gate schedule (harness §3 pattern; TE-1 milestones only)

| Gate | After | Agents | Diff scope |
|---|---|---|---|
| G-V1 | day 4 | vv, cold-reviewer, spec-guard | V-D1..3 |
| G-V2 | day 8 | vv, cold-reviewer, spec-guard, ux-reviewer, architect | V-D4..6 |
| G-V3 | day 11 | vv, cold-reviewer, spec-guard, ops-engineer | V-D7..8 |
| G-V4 | day 14 | spec-guard final sweep, vv full, ops-engineer | V-D9..10 + full |

All agents: TE-2 diff-only, TE-6 15-call budget, TE-8 verdict format,
TE-11 pinned toolchain. FAIL = milestone stops (TE-10); K-2 stop rule on
twice-failed fixes.

## 3. Standing regressions (every gate)

Full v1 suite green (exit-code check, never grep); golden report JSON
byte-identical on fixtures; T-NFR-01 import guard; FR-23 verbatim; stats
policy grep; X-scope grep (updated for the SSR+htmx relaxation).

## 4. Spec ambiguities — numbered questions for founder ruling

1. **Reduced detector set (T2)**: propose D2 (cached-token fields) +
   model-mix analysis only, all others labeled "requires per-request
   rows". Confirm the exact set and the report wording.
2. **First-connect backfill**: how far back do we pull on connect
   (propose 30 days where the provider API allows)?
3. **Scheduler mechanism**: propose ofelia hourly tick → in-app due-work
   queue (deterministic, testable). Approve?
4. **New dependency**: `cryptography` (Fernet + HKDF) for source-key
   encryption — approval per dependency precedent (pyyaml/multipart).
5. **Free tier**: "1 one-shot audit" = upload path, full report, one per
   account forever? Reuses comp-credit machinery or a distinct plan flag?
6. **Source accounting**: does upload/CLI count against Pro's "1 source",
   or are uploads always allowed and only Connect sources metered?
7. **Savings Statement anchor**: calendar month or subscription
   anniversary? Recipients: account email only, or optional CC field?
8. **savings_realized**: USD only? Editable after entry? Owner-only?
9. **VERIFIED headline formula**: propose verified = Σ savings_realized
   (where entered) + Σ delta-confirmed Applied findings; everything else
   labeled estimate. Confirm formula + zero-state copy.
10. **Alert delivery**: email-only in v1.5? Default thresholds and a max
    alert frequency (immediate vs daily digest fold-in)?
11. **Payment routing**: Razorpay for INR / Stripe for USD by user
    choice? Trial? Proration Pro→Team? Downgrade at period end?
12. **Dunning**: retries/grace before lapse; on lapse, scheduled audits
    pause (propose) or cancel?
13. **htmx**: vendored static file, version pinned — confirm (no CDN per
    standing rule).
14. **FR-31 depth**: metadata rows retained indefinitely (propose) or
    windowed?
15. **Hero A/B mechanics**: true split (cookie-bucketed, counts in daily
    digest) — propose — or manual sequential swap?
16. **Walkthrough slot** (hard condition c): propose day 3. Confirm
    date/time.
17. **Early-access emails**: any migration/comms to the captured
    early-access list at v1.5 launch, or leave untouched?
18. **Day-45 gate metric**: restarted gate measures subscription MRR +
    one-shot revenue combined? Same $ target as before?

## 5. Risks (recorded, no action without ruling)

- Provider Usage/Admin APIs are aggregate-granularity and rate-limited;
  detector coverage on T2 is honestly narrower than uploads — sales copy
  must not blur this (WP-7 copy review point).
- VPS is 4 vCPU: weekly auto-audits + daily pulls + interactive uploads
  share MAX_CONCURRENT_AUDITS=2; scheduler must queue, never pile up
  (T-SCH-02). Box upgrade is a founder call if Team-tier load arrives.
- Subscriptions double the webhook surface; FR-27 rails are the
  regression bar (T-SUB-01 replay tests both providers).

— END. Awaiting founder approval of this plan + rulings on §4. No
application code until then.
