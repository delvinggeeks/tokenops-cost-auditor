# LIFECYCLE-MAP — the one auditable view of the full lifecycle

_Consolidated 2026-07-28 from repo ground truth (every row verified in code/docs that day;
nothing carried from chat memory). Answers one question: is the entire
collect → analyze → learn → react → fix → prove → allocate → govern lifecycle designed,
and what is each piece's status and trigger?_

**This file OWNS completeness-view only.** Sequence lives in `QUEUE.md`; requirement detail
lives in the linked sources; nothing here is buildable unless it is a QUEUE NOW task.
Proposed maintenance law (founder to ratify): any ruling that adds/moves a lifecycle
capability updates this table in the same commit.

Status: ✅ shipped · 📋 registered/spec'd (trigger named) · 🚫 forbidden until trigger ·
🟡 candidate in QUEUE · ❓ gap with no recorded home

| Capability | Pillar | Status | Authority | Trigger / evidence |
|---|---|---|---|---|
| **COLLECT** | | | | |
| T1 file upload / CLI (Anthropic+OpenAI JSONL, generic CSV) | P1 | ✅ | docs/12 §Stage-1 | `services/ingest/*` → docs/04 |
| T2 account connect (official Usage/Admin APIs; coarse aggregate — 3 of 9 detectors feed) | P1 | ✅ | R-CONNECT | docs/04; honesty note in findings-depth law |
| T3 collector daemon (pipx watcher, counts-only) | P1 | 📋 | R-CC-LINK | ← post-launch |
| T4 OTLP stream (OTel GenAI semconv; content dropped at door) | P1 | 📋 spec written | docs/13 + R-STANDARDS | ← first 3 customer conversations; carries R-AGENTIC-DIMENSIONS + R-RAG |
| T5 in-VPC gateway | P3/P4 | 🚫 | docs/12 §Stage-1 | ← first enterprise deal where procurement requires in-VPC (recorded 2026-07-22) |
| **ANALYZE** | | | | |
| Deterministic engine — 9 detectors (d1–d6, d8–d10), $-quantified | P2 | ✅ | docs/01 + money law | `services/rules/` goldens + `scripts/pricing_verify.py` (R-AUTO-PRICING) |
| D7 export-candidate detector | P2 | 📋 | R-ZTA (b), BACKLOG:107 | ← day-45 (QUEUE PARKED) |
| Behaviour reading: BEHAVIORAL shapes (detectors) + DECLARED tags (`pct_attributed`) — never content | P2 | ✅ law + partial surface | docs/12 INTENT LAW | full dev-facing lens = T-F3 🟡 |
| **LEARN** | | | | |
| L0 feedback labels (applied / dismissed / not_relevant) | P2/P5 | ✅ | docs/12 §Stage-3 | `services/flywheel/frame.py:70` |
| L1 peer benchmarks | P1 | 📋 part-scaffolded | docs/12 §Stage-3 | ← n≥10 opted-in workspaces; `flywheel/{benchmarks,cohort}.py` exist |
| L2 adaptive detector thresholds | P2 | 📋 | M-FLY-2 | ← n≥25 Applied/Dismissed labels |
| L3 predictive spend + agent-session anomaly | P1/P4 | 📋 | docs/12 §Stage-3 | ← n≥50 audits + 6mo history |
| L4 policy learning | P4 | 🚫 | docs/12 §Stage-3 | ← control-plane era (T5 trigger) |
| Model FACTORY: separate repo, daily eval-gated CI, versioned artifacts behind flag | — | 🟡 T-F1 | R-MODEL-FACTORY 2026-07-28 | evals-only until Stage-3 thresholds fire |
| Cross-workspace aggregate export + consent (k-floor n≥10) | — | 🟡 T-F2 | R-MODEL-FACTORY + R-ZTA | sole lawful data path into the factory |
| **REACT (observe-only, X-02)** | | | | |
| Alerts: SOFT_BUDGET / SPEND_SPIKE / WASTE_ABOVE, configurable thresholds, AlertEvent + email | P4 | ✅ | PLAN-V15 WP-3b | `services/alerts/rules.py:33` — "OBSERVE ONLY (X-02)" |
| Quotas / rate limits / enforced policies on customer traffic | P4 | 🚫 | X-02 | ← T5 era; humans approve policies, machines enforce, audit-logged |
| **FIX (dev persona)** | | | | |
| Per-detector remediation copy; COPY LAW depth (c) — operator handed wins, never at fault | P2 | ✅ | docs/12 COPY LAW | `services/rules/detector_copy.py` |
| Copilot fix guidance | P2 | ✅ | PLAN-COPILOT | metering flagged 2026-07-27 |
| Behaviour lens v1 — shape chips + fix-first copy on breakdown + read API | P2 | 🟡 T-F3 | R-MODEL-FACTORY | QUEUE CANDIDATES |
| **PROVE (owner persona)** | | | | |
| Savings Statement — VERIFIED headline only, provenance stamps, honest empty | P5 | ✅ | R-Q9 + R-STMT-MONTH | `services/statements/build.py` (`verified_usd`, "only called verified…") |
| Cross-audit drift (browser) | P5 | ✅ | docs/04 | `services/dashboard/drift`; API surface 🟡 (parked by #85) |
| Per-finding realized delta → statement | P5 | 🟡 T-F4 | R-MODEL-FACTORY | scope-check first — may collapse into R-Q9 machinery |
| Dogfood self-audit (32.5%) | P5 | ✅ | WP-SELF | self-audit ledger + CI drift gate |
| **ALLOCATE** | | | | |
| by_model / by_route $ allocation + `pct_attributed` honesty | P5 | ✅ | docs/04 | `services/dashboard/tokenomics.py` |
| Showback export for finance (tag/route cost CSV) | P5 | 🟡 | registered 2026-07-28 | QUEUE CANDIDATES |
| Per-agent / per-task / per-chain attribution | P5 | 📋 | R-AGENTIC-DIMENSIONS | ← T4 build (semconv agent spans) |
| Chargeback models (cost-center owners, internal billing) | P5 | ❓ | none | founder call: register or reject |
| **GOVERN (our product, never their traffic)** | | | | |
| Workspaces, 4-role RBAC, scoped read tokens, INSERT-only auditlog, FR-22, API rate limits | P4 | ✅ | R-ORG, FR-21/22, NFR-03 | `services/lifecycle/auditlog.py` et al. |
| SSO · SCIM · IAM CRUD / service accounts / custom roles | P4 | 📋 | R-IAM, O-3 | ← first team customer (SSO); design registered |
| **PLATFORM (enabler)** | | | | |
| Read API (audits, audit, findings, breakdown) + OAuth + JS SDK read methods | — | ✅ | R-PLATFORM S-6 | #72/#83/#86; docs-site regenerated gate |
| MCP server (list_audits, list_findings) | — | ✅ | S-3 | `mcp/server.py:45`; get_audit/get_breakdown parity 🟡 |
| savings / sources read endpoints | — | 🟡 | pre-registered by #83 | QUEUE CANDIDATES |
| OTel GenAI + FOCUS standards adoption | — | 📋 recorded law | R-STANDARDS | implemented at T4 build, not before |
