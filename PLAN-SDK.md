# PLAN-SDK — the Sentry adoption model for TokenOps Cost Auditor

**Status: AWAITING FOUNDER RULING (like PLAN-TAAS before its "proceed").**
Order source (founder, 2026-07-23, verbatim in substance): "I want this
platform to be built and used like Sentry in all the dev platforms and
enterprises — check their workflows: configurations sitting in clients'
environments, APIs, MCP, etc. Our platform design has to be built the
same way: configs, SDKs, settings."

Grounding: Sentry's adoption mechanics verified two ways today — their
public workflow (install SDK → paste DSN → sensible defaults → first
event lands → integrations ecosystem; self-hosted for regulated
environments) AND hands-on: we integrated sentry-sdk into our own stack
this same day (WP-DEVOPS-OBS), so the DSN/init/scrub/release model below
is drawn from direct experience, not reading.

## 0. The honest map — Sentry pillar → our equivalent → status

| Sentry pillar | Ours | Status |
|---|---|---|
| One paste-able DSN carrying endpoint+credential+project | NOTHING unified — collector uses X-Device-Token, connectors store provider keys, uploads use sessions | **NEW: S-0** |
| SDK with sensible defaults, auto-instrumentation, init-and-done | T3 collector (Claude Code transcripts) is the nearest thing; no in-process SDK | **NEW: S-1** |
| "Point existing telemetry at us" (zero code) | T4 OTLP ingest — SPEC EXISTS (docs/13, WP-T4-SPEC), endpoint build gated on separate approval | **BUILD: S-2** |
| Config in the client's environment (env var + config file) | Collector has ~/.config/tokenops-cost-auditor/device.json only | **NEW: S-0** |
| Release/environment dimensions on every event | source labels exist; no env/service/team tags | S-0 carries tags |
| Self-serve onboarding with "waiting for first event" | R-LIVE-AUDIT pipeline theater + link-code flow — the pattern EXISTS | EXTEND: S-1 |
| API + webhooks for automation | /api/v1 (FR-25/26) exists; no outbound webhooks | PARTIAL; S-5 |
| MCP for AI dev tools | nothing | **NEW: S-3** |
| Integrations (GitHub/Slack/CI) | mail alerts only | **NEW: S-5** |
| Self-hosted for regulated envs | R-DEPLOYMENT-CONTRACT: single artifact, BYO postgres, air-gap — ALREADY LAW | EXISTS |

## 1. The DSN (S-0 foundation) — one string in the client's environment

`TOKENOPS_COST_AUDITOR_DSN=https://ik_<key>@tokenops-cost-auditor.com/w/<workspace>`
(full product name in the env var — R-NAMING; self-hosted deployments
swap the host and nothing else changes.)

- The key is INGEST-ONLY and scoped: it can POST usage records and read
  nothing — a leaked DSN cannot exfiltrate a byte (mirrors Sentry's
  public-DSN posture, honestly stated). Hashed at rest on the existing
  HKDF path (the device-token discipline).
- Minted/revoked on the Sources page (the machines-list grammar);
  fingerprinted; audit-logged.
- Config file convention `tokenops-cost-auditor.yaml` (repo root or
  ~/.config/tokenops-cost-auditor/): workspace, source label,
  environment, tags (service/team — the future per-team GROUP BY the T4
  spec already notes). DSN itself stays in env, never in the file.
- New endpoint POST /api/v1/ingest: per-call usage records (T1-grade
  tier: FULL six-detector coverage), FR-26 idempotency, FR-22 at the
  door (counts/hashes only accepted; text fields rejected loudly).

## 2. The SDK (S-1) — init-and-done, counts-only BY CONSTRUCTION

```python
import tokenops_cost_auditor
tokenops_cost_auditor.init()  # DSN from env; that's the whole setup
```
- Auto-instruments the OpenAI + Anthropic client libraries (integration
  registry, Sentry-style): wraps responses, extracts model + token
  counts (incl. cache read/write) + timestamp + latency + status. The
  prompt/completion text is NEVER SERIALIZED — FR-22 by construction,
  provable in the SDK's own tests.
- Observe-only, X-01 SAFE: the SDK never sits in the request path, never
  retries/blocks/modifies traffic; a dead network drops records silently
  rather than slowing the caller (background batcher, bounded queue).
- Ships batches to /api/v1/ingest with idempotency keys; release/env/
  tags attached from config.
- Per-call records mean d4 retry storms and d6 chatty loops work — the
  SDK tier gives FULLER coverage than the provider connectors.
- Distribution: the existing `tokenops-cost-auditor` package (PyPI
  publish is already founder-lane) — one package, full name, CLI + SDK.
- Onboarding: Sources gains an "SDK" card → mint DSN → copy snippet →
  the live theater waits for the first batch (R-LIVE-AUDIT pattern).

## 3. Proposed slices (each VERTICAL per rule 9, gates per TE)

- **S-0 Ingest DSN + endpoint + config convention** (~2d): key mint/
  revoke UI, /api/v1/ingest, yaml convention, docs. DoD: journey = mint
  → curl a batch → audit lands → report reachable.
- **S-1 Python SDK** (~2-3d): integrations for openai/anthropic libs,
  batcher, init(), SDK card + first-data theater, quickstart docs,
  FR-22-by-construction test suite. DoD: a demo app with the SDK shows
  its calls on the dashboard without any export step.
- **S-2 T4 OTLP endpoint** (~2-3d): build docs/13 as specced (OTel GenAI
  semconv → CallRecordFrame, content attributes dropped at the door).
  This order supersedes the "first 3 customer conversations" gate the
  same way the TaaS order superseded its trigger — CONFIRM (Q2).
- **S-3 MCP server** (~1-2d): `tokenops-cost-auditor mcp` (stdio) with
  read tools — get_spend, get_findings, get_run_status, latest_report —
  so AI dev tools sit ON the platform. Write tools deferred.
- **S-4 JS/TS SDK** (later): second language, same laws.
- **S-5 Integrations** (later): GitHub Action (audit summary on PR),
  Slack alert delivery (X-02: notify, never enforce).

## 4. X-scope analysis

The SDK observes and reports; it never proxies, never gates, never
alters a request (X-01/X-02 stand). Enforcement stays out. The MCP
server reads; the one "action" tool (audit_now) maps to an existing
customer-triggered action. No LLM narrative anywhere (X-04).

## 5. Open questions for the founder

- Q1: Approve S-0 + S-1 as the next cards after C-C (or before it)?
- Q2: Confirm S-2 supersedes the T4 spec's conversation-count gate?
- Q3: MCP stdio-first (ships with the CLI) — hosted MCP later?
- Q4: SDK captures latency + HTTP status per call (needed for d4/d6
  full coverage) — counts and milliseconds only, no content. Confirm?
- Q5: PyPI publish (founder-lane) becomes a blocker for S-1 adoption —
  schedule it with S-1?
