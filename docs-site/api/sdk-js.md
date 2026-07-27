# JS/TS SDK

The official TypeScript/JavaScript SDK — send usage (**counts only**) and read your
audits and findings from Node, an edge worker, or the browser. Source: `sdk/js`.

- **Counts-only by construction.** `UsageRecord` has no field for prompt or completion text, so you cannot send it (FR-22).
- **Two credentials, two capabilities.** An **ingest key** (`ik_…`, write-only) sends usage; a **read token** (`rt_…`, read-only) reads audits + findings.
- **Zero runtime dependencies** — uses the platform `fetch` (Node 18+, browsers).

## Install

```bash
npm install tokenops-cost-auditor
```

## Send usage

```ts
import { TokenOps } from "tokenops-cost-auditor";

const client = new TokenOps({ ingestKey: process.env.TOKENOPS_COST_AUDITOR_KEY });

const { audit_id } = await client.ingest([
  { ts: "2026-07-24T10:00:00Z", provider: "openai", model: "gpt-5.4",
    prompt_tokens: 3084, completion_tokens: 47, cached_tokens: 0 },
]);
```

## Read audits and findings

```ts
const client = new TokenOps({ readToken: process.env.TOKENOPS_COST_AUDITOR_TOKEN });

const audit = await client.waitForAudit(audit_id);      // polls List audits until done/failed
if (audit.status === "done") {
  for (const f of await client.listFindings(audit_id)) {
    console.log(`${f.detector}  ${f.severity}  $${f.monthly_cost_impact_usd}/mo — ${f.fix}`);
  }
}
```

## Errors

Any non-2xx throws `TokenOpsError` with `.status` and `.detail` (the API error envelope) —
for example a read token missing a scope raises a `403`. See the
[error catalog](reference.md) for every code.

## API

| Method | Credential | Endpoint |
|--------|-----------|----------|
| `ingest(records)` | ingest key | `POST /api/v1/ingest` |
| `listAudits()` | read token (`read:audits`) | `GET /api/v1/audits` |
| `listFindings(id)` | read token (`read:findings`) | `GET /api/v1/audits/{id}/findings` |
| `waitForAudit(id)` | read token | polls `List audits` |

The Python SDK and the raw HTTP contract are in the [reference](reference.md).
