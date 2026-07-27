# tokenops-cost-auditor (JS/TS SDK)

The official TypeScript/JavaScript SDK for [TokenOps Cost Auditor](https://tokenops-cost-auditor.com).
Send usage (**counts only**) and read your audits and findings — from Node, an edge worker, or the browser.

- **Counts-only by construction.** `UsageRecord` has no field for prompt or completion text, so you cannot send it (FR-22). The SDK never sits in your request path.
- **Two credentials, two capabilities.** An **ingest key** (`ik_…`, write-only) sends usage; a **read token** (`rt_…`, read-only) reads audits + findings. Mint both under **Sources → SDK & API** / **Developer → API tokens**.
- **Zero runtime dependencies.** Uses the platform `fetch` (Node 18+, browsers).

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
console.log("audit:", audit_id);
```

## Read audits and findings

```ts
const client = new TokenOps({ readToken: process.env.TOKENOPS_COST_AUDITOR_TOKEN });

const audit = await client.waitForAudit(audit_id);           // polls until done/failed
if (audit.status === "done") {
  for (const f of await client.listFindings(audit_id)) {
    console.log(`${f.detector}  ${f.severity}  $${f.monthly_cost_impact_usd}/mo — ${f.fix}`);
  }
}
```

## Errors

Any non-2xx response throws `TokenOpsError` with `.status` and `.detail` (the API's
error envelope), e.g. a read token missing a scope raises a `403`:

```ts
import { TokenOpsError } from "tokenops-cost-auditor";
try {
  await client.listFindings(audit_id);
} catch (e) {
  if (e instanceof TokenOpsError && e.status === 403) console.error(e.message);
}
```

## Options

| Option | Purpose |
|--------|---------|
| `ingestKey` | `ik_…` write-only key — required for `ingest` |
| `readToken` | `rt_…` read-only token — required for `listAudits` / `listFindings` |
| `baseUrl` | API origin (defaults to the hosted instance) |
| `fetch` | inject a custom `fetch` (tests, non-standard runtimes) |

Full API reference: <https://docs.tokenops-cost-auditor.com/api/reference/>.
