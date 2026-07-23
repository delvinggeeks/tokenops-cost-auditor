# KANBAN — the whole platform, as cards (founder order 2026-07-23)

The standing law behind every card: a card is DONE only when the uniform
DoD held — tests per docs/05 pattern + traceability same commit + golden
NOTES for money math + FR-22 tier tests + honesty-law rendering + gate
verdicts (TE-8) + ux mockup-before-wiring on new surfaces + STATUS
paragraph + conventional commits + ≤3-day slices + R-VERTICAL: the slice
contains its UI, click path, journey test and ux gate — a user finishes
the job inside the one milestone, never a layer at a time. Sources of truth:
docs/00-07/11/12/13, PLAN.md, PLAN-V15.md, PLAN-FLYWHEEL.md, PLAN-TAAS.md,
BACKLOG.md, STATUS.md, CHANGELOG.md. This board is the MAP; those are the
territory.

## ✅ DONE — shipped, gated, in production

**Ring 1 wedge — Audit product v1.0 (D1–D14, live since 2026-07-20)**
- Ingest T1: OpenAI/Anthropic JSONL + CSV + Claude Code exporter (FR-01..04, FR-24)
- Versioned four-rate pricing + golden discipline (FR-05/06, R-Q3/Q4)
- Six deterministic detectors, zero inference (FR-07..13, NFR-01 guard)
- Report JSON/PDF/web + signer + methodology (FR-14..16, FR-28/30)
- Auth, payments (Razorpay+Stripe), admin, purge lifecycle, ops (FR-17..23, FR-25..29, NFR-02..15)

**Monitor v1.5 (WP-1..7, live)**
- T2 Connect OpenAI+Anthropic (wizards, HKDF/Fernet keys, honest reduced coverage)
- Owner dashboard (three depths, help registry), alerts observe-only, L0 feedback,
  Savings Statement (R-Q9 verified math), settings, subscriptions + dunning,
  federated sign-in, live pricing sync (R-LIVE-PRICING), daily digest loop

**The founder-order day (2026-07-23, v1.6.0–v1.6.6 — 8 gated milestones, 6 prod deploys)**
- FR-32 Report explorer: full-history filters, per-account switching, saved
  views (whitelist-sanitized; export HELD on its trigger) — v1.6.0/1a475a7
- R-MULTI-SOURCE: multi-account connect, key-fingerprint dedup,
  audits.source_id (migration 013) — v1.6.0
- R-ICON-ACTIONS compact account cluster · R-PIPELINE-LIVE animated live
  spine · R-LIVE-DASH audit-landed refresh, zero idle polling — v1.6.0
- R-SYSTEM-TEST + R-REACHABILITY: journey suite, system-tester gate,
  declared=click-reachable law. Day ledger: 15+ sweeps, ~15 real bugs
  fixed pre-customer, 2 founder finds converted to laws — v1.6.0/v1.6.3
- R-F1-SIGNOFF: amended data promise on all five surfaces + benchmark
  toggle (default ON disclosed, audit-logged, migration 015) — v1.6.0
- M-FLY-0 flywheel spine: training-frame contract (FR-22-as-schema,
  pseudonyms, R-F1 exclusion at first byte) + cohort ledger (Honesty-Law
  rungs, founder surfaces only) — v1.6.1
- M-FLY-1 L1 peer benchmarks: dashboard + report, dormant-until-n≥10,
  goldens founder-verified, leakage law pinned, one rank policy on every
  path (cold FAIL fixed) — v1.6.1
- Connect-journey hardening from four founder reports: every provider
  linked everywhere (R-CONNECT-VISIBLE), admin plan grants (R-DOGFOOD,
  runbook §9), console-link trust notes, the org-only Admin-keys wall
  taught, account-shapes routed guide — v1.6.2..v1.6.6
- WP-T4-SPEC: the OTel/OTLP ingest mapping contract (docs/13) — endpoint
  build remains a separate approval
- Rulings recorded: R-PROCEED (TAAS Q1-5, FLYWHEEL Q4-7), TE-5 tiering
  (Fable designs · Opus implements · Sonnet gates)
- WP-CC-LINK T3 collector: consent-first device link (hashed one-shot
  codes, TTY-only 'I agree', revoke deletes key material), FR-26
  idempotent ships via the T1 pipeline, machines list on Sources,
  R-NAMING full-name pin — v1.6.7/v1.6.8 (migration 016)
- WP-PIPELINE-UI runs observatory (FR-31 closed): /runs ledger with
  kit-ribbon stage drill-ins from recorded StageEvents (both pipelines,
  honest detector zeros), pull ledger incl. user-safe failures, alert
  checks ("silence you can verify"), purged rows metadata-only, in-flight
  self-poll, F14 CSS dedup; gates spec PASS · vv PASS · cold PWN fixed ·
  system-tester PWN fixed (cent-drift reconciliation) · ux v2 PWN —
  migration 017, pending deploy v1.6.9

## 🔜 NEXT — ruled order, nothing moves without a new ruling

1. **WP-CLOUD-T2** — C-A Azure OpenAI + C-B Bedrock BOTH BUILT+GATED
   2026-07-23; pricing sections G16-G23 AGENT-VERIFIED 31/31 per
   R-AUTO-PRICING (no human gate) — v1.7.0 ready on deploy approval;
   C-C Gemini/Vertex next → (4-6d total, one slice each) — C-A Azure OpenAI →
   C-B Bedrock → C-C Gemini/Vertex. DoD per slice: fixture-driven adapter,
   founder-verified golden pricing rows BEFORE merge, FR-22 tier tests,
   wizard + illustration, journey additions.
2. **WP-COPILOT-AGG** (2d) — Copilot admin seat/credit export ingest
   (upload path, no API dependency), seat-waste findings.
3. **M-FLY-2** (2.5-3d) — L2 threshold calibration, SHADOW mode (report
   JSON block only, findings byte-identical); B3 activation behind
   founder flag after ≥1 month shadow evidence.
4. **Landing "Works with" rider** (0.5d) — five tiers stated plainly,
   Cursor/Lovable truth included; rides the next landing touch.
5. **WP-PLAT-0** — monorepo migration (apps/ + wa-* packages); acceptance
   gate = suite green + byte-identical golden report JSON.

## ⏸ TRIGGERED — parked by rule; fires on its event (BACKLOG.md is the register)

API keys + WP-MCP (first request = buying signal) · orgs/SSO (first team
customer) · SOC2 (procurement blocker) · Helm (first VPC customer) ·
marketplace IaC (second enterprise deal) · T4 OTLP endpoint (separate
approval; spec done) · T5 in-VPC gateway (procurement demand) · C3
view-export (data-export trigger) · D7 export-candidate detector + playbooks
(day-45) · RAG pack (≥2 RAG-heavy customers) · night-audit mood · Indic
locales · org-fingerprint hardening (first double-connect incident or
provider OAuth) · self-hosted vLLM metering (first such customer) ·
queue/workers (cap saturation) · Cursor/Lovable adapters (their API existing
+ a request) · L3 learned forecast (n≥50 + 6mo) · L4 policy learning
(control-plane era) · Build Health + Comprehend rings (day-45 gate).

## 🧑‍💼 FOUNDER — only you can move these

- Launch thread + day-45 revenue gate restart (assets exist; rails attached)
- UptimeRobot public status page + CNAME (standing task list item 1)
- Stripe dashboard credentials for the global payment link
- PLAN-TAAS/FLYWHEEL leftovers: none open — next ruling needed only when a
  trigger fires or the queue order should change

**Honest completion statement:** Ring 1 (SPEND: audit → monitor →
intelligence L0/L1) is COMPLETE and live. The platform vision (PLAN §0.0)
is three rings — DISCIPLINE and COMPREHENSION are day-45-gated by your own
sequencing, and the control plane waits for its procurement trigger. The
board is finished when the triggers fire and their cards cross; the queue
is never silently reordered.
