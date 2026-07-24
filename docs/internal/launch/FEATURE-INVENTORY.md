# Feature inventory — everything we planned, and where it stands

Founder order 2026-07-22: "implement all the features and ideas we planned
without missing any." Method: three parallel sweeps over the full record
(requirements+traceability; every PLAN §0.1 ruling with a build obligation;
BACKLOG + flywheel trigger register). Result below. One genuine gap was
found and closed the same day (R-ARCH-PATTERNS(a)); everything else is
either SHIPPED with a deploy tag, YOURS to activate, or deferred BY YOUR
OWN RULING with a named trigger.

## 1. The three things the order named — all shipped

- **Connecting LLM accounts, securely** (v1.5.0→): connect wizard with
  read-only API keys; credentials envelope-encrypted at rest (HKDF/Fernet,
  T-KEY-01..03); revoking a source deletes the ciphertext (R-Q5/Q6);
  counts-only forever (FR-22); daily pulls, weekly audits, plan-gated
  (R-FREE-CONNECT: Free = 1 connection, 1 metered audit).
- **Federation** (v1.5.12/13): Google + Microsoft (Entra) + GitHub, one
  registry, each config-gated on its full credential pair, CSRF state
  cookie-pinned, verified-emails only, one signup credit through every
  door. Apple + SAML/Okta parked with triggers (BACKLOG).
- **Tokenomics algorithm models** (D3–D5, v1.5.0→): six deterministic
  detectors (oversized model, missing cache, prompt bloat, retry storms,
  unbounded max-tokens, chatty loops — FR-07..12, golden-pinned) + three
  aggregate detectors (R-Q1) + founder-verified rate card (NFR-15) +
  verified-savings statements (R-Q9) + daily digest/budget staging
  (R-DAILY-LOOP, v1.5.14). Zero LLM calls in the engine (NFR-01).

## 2. Requirements sweep: every MUST implemented except one — by ruling

All M-priority FR/NFR rows carry module + test evidence (spot-checked).
The single exception: **FR-31 "My audits" history list** — moved by YOUR
R-PIPELINE-UI-SEQ (Option A) into WP-PIPELINE-UI, the first post-launch
milestone; its pre-launch carve-out (live pipeline theater + row-errors
download) shipped v1.5.2. Traceability row now records the supersession.
Minor label drift noted (T-REP-09/T-API-06/T-API-07 ids not verbatim in
test files; the behaviours are tested under other names) — cosmetic.

## 3. Rulings sweep: one gap found → closed today

**R-ARCH-PATTERNS(a)** (2026-07-22): the docs-site "Architecture
principles" cited-claims section (zero-token engine, zero-trust five axes,
five-gate validation ladder) was ruled and never built. Built now in
docs-site/engineering/architecture.md, every claim citing its FR/NFR/test
id; the (d) law quoted; the (b) sales line stays REGISTERED-NOT-RELEASED
per the launch-assets register. Everything else in the rulings ledger:
SHIPPED (tags v1.5.0–v1.5.14 in CHANGELOG) or founder-owned/post-launch.

## 4. Founder-owned activations (blocking only what you choose)

Status page CNAME (§3b) · walkthrough ACCEPT · payment links at LAUNCH
prices + webhook secrets (§3a) · OAuth credentials per provider (§3a) ·
hosted-page price flip when the ops digest says cohort FULL ·
provider-side closures per digest.

## 5. Deferred BY RULING — the override menu (say "BUILD n" to pull one forward)

1. FR-31 runs/audits list + per-stage drill-in — WP-PIPELINE-UI, first
   post-launch gate (R-PIPELINE-UI-SEQ).
2. WP-REPORT-VISUAL report styling — same milestone family.
3. WP-CC-LINK Claude Code collector (T3) — days post-launch, 2-3 days.
4. API keys + MCP surface — first customer request (a buying signal).
5. More provider connectors (Gemini/Bedrock/Azure-OpenAI; Cursor/Lovable)
   — pull-sequenced per first request each (R-AGNOSTIC).
6. T4 OTLP streaming (+ k8s attribution) — spec after 3 customer
   conversations; build at first streaming customer.
7. T5 in-VPC gateway / Helm / marketplace — deployment-contract governed,
   first VPC customer.
8. Teams/SSO/orgs — X-03 trigger (first team customer).
9. Data export, payment API adapters, PWA — R-SAAS-BASICS triggers.
10. WhatsApp digest · success-fee experiment · Apple sign-in ·
    self-hosted-inference metering · queue/workers · SOC2 — each with its
    registered trigger in BACKLOG.

## 6. Parked items — triggers REGISTERED (founder "approved proceed" 2026-07-22)

All nine now carry explicit firing conditions in BACKLOG.md / the flywheel:
task-declaration → T4 spec conversations · Act-stage playbooks → rides the
D7 detector's trigger · Night Audit mood → first on-call customer request ·
Indic locales → 25% India-billed base or first hi-IN request · dark mode →
superseded in-app by the aura toggle, public-site toggle on first request ·
public changelog → first post-launch docs batch · control-plane early
access → 25 cumulative signups notifies the founder · concierge onboarding
→ automates at >5 new paying customers/week · T5 GATEWAY → first deal where
procurement states in-VPC as blocking · F11-F16 → fold into
WP-PIPELINE-UI/WP-REPORT-VISUAL, whichever touches each surface first.
Nothing in the record is now untracked: every idea is shipped, founder-
owned, or trigger-registered.
