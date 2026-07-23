# docs/13 — T4 STREAM ingest spec (WP-T4-SPEC; R-PROCEED 2026-07-23)

Status: SPEC APPROVED TO EXIST (R-PROCEED Q2 superseded the
first-3-conversations gate). **The endpoint build remains a separate
founder approval** — this document is the mapping contract it will be
built against, so the first customer conversation can happen against a
written spec instead of a promise.

Laws inherited whole: FR-22 counts-only AT THE DOOR; NFR-01 (no inference
anywhere near the engine); docs/12 Stage-1 frame contract (provenance +
dedup stats per row; per-tier detector coverage honestly declared);
R-AGENTIC-DIMENSIONS 1 and R-RAG 1 (agent + RAG dimensions preserved);
R-STANDARDS (FOCUS-aligned export unchanged by this spec).

## 1. Wire protocol

- OTLP/HTTP at `/api/v1/otlp/v1/traces` (standard OTLP path shape),
  protobuf and JSON encodings; gzip accepted.
- Auth: per-source ingest token — a new `Source` type `otlp` issued in the
  dashboard (device-token grammar of R-CC-LINK: scoped, revocable, never a
  provider key). Revoke stops ingest; data already landed follows normal
  lifecycle.
- Idempotency: span_id is the request identity; re-exported spans upsert
  (max-complete usage wins — the UAT-D5 law at streaming granularity).
- Backpressure: 429 + Retry-After on the NFR-12 limiter; OTel exporters
  retry natively, so honest refusal is safe.

## 2. Attribute mapping — gen_ai.* → CallRecordFrame

The GenAI semantic conventions are EXPERIMENTAL upstream; ingest reads
BOTH the current and prior attribute names (dual-version law) and records
which version each row arrived under in provenance.

| CallRecordFrame | OTel source | Notes |
|---|---|---|
| ts | span end timestamp | UTC (NFR-11) |
| provider | `gen_ai.system` | e.g. openai, anthropic, aws.bedrock |
| model | `gen_ai.response.model` else `gen_ai.request.model` | response wins (actual biller) |
| prompt_tokens | `gen_ai.usage.input_tokens` (legacy: `gen_ai.usage.prompt_tokens`) | |
| completion_tokens | `gen_ai.usage.output_tokens` (legacy: `completion_tokens`) | |
| cached_tokens | provider-specific attrs when exporters emit them | no stable semconv yet — mapped per provider, declared in provenance |
| latency_ms | span duration | |
| endpoint | `gen_ai.operation.name` | chat, embeddings, … |
| request_id | span_id | provider request ids kept in raw_extra when present |
| tags | `service.name`, `k8s.namespace.name`, `k8s.deployment.name`, `k8s.pod.name`, `gen_ai.agent.id`/`.name`, trace_id | the attribution dimensions |

**DROPPED AT THE DOOR, unconditionally (FR-22):** `gen_ai.prompt.*`,
`gen_ai.completion.*`, message-content events, tool-call argument
payloads, and any attribute whose value is free text beyond enum/id
shape. The drop happens before any row is constructed; a content
attribute never exists in our process beyond the parse frame.

## 3. The dimensions this unlocks (registered rulings, now concrete)

- **Per-agent / per-task / per-chain** (R-AGENTIC-DIMENSIONS 1):
  `gen_ai.agent.*` + trace linkage land in tags → cost-per-agent and
  chain attribution become GROUP BYs; per-agent findings become standard
  report sections at build time.
- **Per-team / per-service tokenomics** (BACKLOG k8s note, now spec):
  k8s resource attributes ride every span already — namespace/deployment
  slicing is a filter in the explorer, not new machinery. No sidecar, no
  eBPF, unless a customer's stack cannot emit OTel.
- **RAG stages** (R-RAG 1): vector-DB query spans map to endpoint=
  `db.vector.query` rows with zero content — cost-per-pipeline-stage and
  per-knowledge-base attribution; every RAG finding carries the
  quality-validation caveat verbatim.

## 4. Honest detector coverage on T4 (declared per docs/12 Stage-1 law)

| Detector | T4 coverage | Why |
|---|---|---|
| D1 oversized-model | FULL | per-call models + completion sizes |
| D2 missing-cache | PARTIAL | cache fields only when exporters emit them; NO prefix evidence — we never see text, so prefix hashing cannot run (unlike T1, where it runs in-memory during parse) |
| D3 prompt-bloat | FULL | per-call prompt sizes per route |
| D4 retry-storm | PARTIAL | timing + size/model similarity; no text-identity evidence |
| D5 unbounded-max_tokens | FULL when `gen_ai.request.max_tokens` present | |
| D6 chatty-loop | FULL | burst/sequence shapes from timing + trace linkage |

Reports state this table's verdicts per audit, same as T2 does today.
Final wording lands with the build gate; NEVER a savings number from a
coverage the tier cannot support.

## 5. Storage and audit shape

Rows land in a `stream_usage` family mirroring `source_usage` semantics
(counts + provenance, additive migration) with per-request granularity
retained as counts-only CallRecordFrames; scheduled audits consume them
through the same runner path as T2 sources. Purge and retention laws
unchanged (FR-21: derived aggregates retained, raw protobuf batches are
never persisted beyond parse).

## 6. Build estimate (for the separate approval)

3-5 days as its own gated milestone: endpoint + dual-version mapping +
`otlp` source type/token UI + fixture-driven tests (recorded OTLP batches,
no live exporters in CI) + journey additions + docs-site page. Fires
naturally on the first streaming-customer conversation — which this spec
exists to make concrete.

— END. Mapping contract of record; amendments here, never in code first.
