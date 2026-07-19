# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

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

## D13 PHYSICAL DEPLOY — LIVE at https://tokenops.cloud (founder GO 2026-07-19; two defects found+fixed)

Deployed via provision.sh one-command path to founder's Contabo VPS 4
(4 vCPU / 7.8 GiB; hardening ran FIRST per founder order: keys-only, ufw,
fail2ban). DNS apex+www+docs all serve with Let's Encrypt TLS; www 301s to
apex; docs-site (new Caddy block + provision step 4c build+rsync) serves
at docs.tokenops.cloud; Postmark SMTP live (mail.sent verified to founder
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
