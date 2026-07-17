# Requirements

The product is specified as functional and non-functional requirements with
IDs (FR-nn / NFR-nn / X-nn). This page groups their intent readably; the
[traceability matrix](traceability.md) maps each ID to code and tests.
<!-- src: docs/01-REQUIREMENTS.md, grouped -->

## Ingestion

Accept OpenAI JSONL, Anthropic JSONL, and a documented generic CSV up to
200 MB; detect format per file; count and report invalid rows instead of
silently patching them; preserve unknown columns as metadata. A local-log
exporter for Claude Code sessions ships with the product (counts only, no
text). <!-- src: FR-01/02/24 -->

## Analysis

Price every call at the provider rate in effect at its timestamp from a
versioned four-rate table; refuse to guess rates for unknown models; run six
deterministic waste detectors; make every estimate conservative and every
haircut explicit. The engine contains zero LLM or network calls — enforced by
an automated import-guard test. <!-- src: FR-05..FR-12; NFR-01 -->

## Reporting

One assembled report model rendered as deterministic JSON, a private web
report, and a client-ready PDF; findings ranked by monthly dollar impact with
severity, confidence, fix text, and up to 20 evidence rows; methodology and
pricing provenance printed in the report. Signed report URLs expire after 30
days. <!-- src: FR-13/14/15/28 -->

## Accounts and payments

Magic-link sign-in (single-use, 15-minute expiry) with secure session cookies;
one payment = one audit credit, consumed atomically; HMAC-verified webhooks
with timestamp tolerance and replay-proof event dedup; a token-gated admin
panel whose every action lands in an append-only audit log.
<!-- src: FR-17/18/19/20/27 -->

## Lifecycle and privacy

Raw uploads auto-purge 7 days after report generation (audit-logged); no
prompt or completion text is ever persisted; the landing page states the data
policy verbatim: "analyzed then deleted; nothing retained beyond 7 days; never
used for training." <!-- src: FR-21/22/23 -->

## Operations

Rate limiting (per-user where possible), a processing concurrency cap with
queue-position reporting, one uniform JSON error envelope, structured logging
with request IDs, daily backups with a documented and drilled restore path,
a pricing table whose staleness is monitored (14-day warning), and a read-only
weekly pricing drift check that can never write the rate card.
<!-- src: NFR-03/12/13/14, NFR-05/08/15, FR-29 -->

## What we commit to NOT building

Out-of-scope is specified with the same rigor as in-scope, as X-requirements:
no live proxy or gateway, no policy/budget enforcement, no multi-org RBAC/SSO,
no LLM-generated narrative in reports, no SPA frontend. See
[Limits](../limits.md) for what these boundaries mean for you.
<!-- src: docs/01 §G X-01..X-05 -->
