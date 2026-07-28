import test from "node:test";
import assert from "node:assert/strict";
import { TokenOps, TokenOpsError, type UsageRecord } from "./index.ts";

/** A fetch stand-in that records the request and returns a canned response. */
function mockFetch(
  status: number,
  body: unknown,
  capture?: (url: string, init: RequestInit) => void,
): typeof fetch {
  return (async (url: unknown, init?: RequestInit) => {
    capture?.(String(url), init ?? {});
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

test("ingest POSTs to /api/v1/ingest with the ingest key as a Bearer", async () => {
  let seen: { url: string; init: RequestInit } | undefined;
  const client = new TokenOps({
    ingestKey: "ik_test",
    fetch: mockFetch(201, { audit_id: "aud_1", records: 1, replayed: false }, (url, init) => {
      seen = { url, init };
    }),
  });
  const records: UsageRecord[] = [
    { ts: "2026-07-24T10:00:00Z", provider: "openai", model: "gpt-5.4", prompt_tokens: 10, completion_tokens: 2 },
  ];
  const res = await client.ingest(records);
  assert.equal(res.audit_id, "aud_1");
  assert.ok(seen);
  assert.match(seen.url, /\/api\/v1\/ingest$/);
  assert.equal((seen.init.headers as Record<string, string>).Authorization, "Bearer ik_test");
  assert.equal(seen.init.method, "POST");
});

test("listFindings uses the read token and returns the array", async () => {
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(200, {
      findings: [{ detector: "oversized_model", severity: "high", monthly_cost_impact_usd: 12.5, fix: "downshift" }],
    }),
  });
  const findings = await client.listFindings("aud_1");
  assert.equal(findings.length, 1);
  assert.equal(findings[0]?.detector, "oversized_model");
});

test("getAudit GETs /api/v1/audits/{id} and returns the summary directly, no envelope", async () => {
  let seen: { url: string; init: RequestInit } | undefined;
  // Byte-for-byte copy of the real get_audit response body shape (routes_api_read.py).
  const fixture = {
    id: "aud_1",
    status: "done",
    scope_label: "openai,anthropic",
    created_at: "2026-07-24T10:00:00Z",
    completed_at: "2026-07-24T10:05:00Z",
    totals: {
      calls: 42,
      input_tokens: 1000,
      output_tokens: 250,
      total_tokens: 1250,
      estimated_cost_usd: 3.75,
    },
    model_count: 2,
    finding_count: 5,
  };
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(200, fixture, (url, init) => {
      seen = { url, init };
    }),
  });
  const audit = await client.getAudit("aud_1");
  assert.ok(seen);
  assert.match(seen.url, /\/api\/v1\/audits\/aud_1$/);
  assert.equal((seen.init.headers as Record<string, string>).Authorization, "Bearer rt_test");
  assert.equal(audit.id, "aud_1");
  assert.equal(audit.status, "done");
  assert.equal(audit.scope_label, "openai,anthropic");
  assert.equal(audit.totals.total_tokens, audit.totals.input_tokens + audit.totals.output_tokens);
  assert.equal(audit.model_count, 2);
  assert.equal(audit.finding_count, 5);
});

test("getAudit URL-encodes the audit id", async () => {
  let seen: { url: string; init: RequestInit } | undefined;
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(
      200,
      {
        id: "aud/1 x",
        status: "done",
        scope_label: "",
        created_at: null,
        completed_at: null,
        totals: { calls: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, estimated_cost_usd: 0 },
        model_count: 0,
        finding_count: 0,
      },
      (url, init) => {
        seen = { url, init };
      },
    ),
  });
  await client.getAudit("aud/1 x");
  assert.ok(seen);
  assert.match(seen.url, /\/api\/v1\/audits\/aud%2F1%20x$/);
});

test("getAudit without a readToken throws before any fetch call", async () => {
  let called = false;
  const client = new TokenOps({
    fetch: mockFetch(200, {}, () => {
      called = true;
    }),
  });
  await assert.rejects(() => client.getAudit("aud_1"), /readToken/);
  assert.equal(called, false);
});

test("getAudit on a 404 raises TokenOpsError with .status === 404", async () => {
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(404, { error: { message: "audit not found" } }),
  });
  await assert.rejects(
    () => client.getAudit("missing"),
    (e: unknown) => e instanceof TokenOpsError && e.status === 404,
  );
});

test("getBreakdown GETs /api/v1/audits/{id}/breakdown and returns the whole response", async () => {
  let seen: { url: string; init: RequestInit } | undefined;
  // Byte-for-byte copy of the real get_audit_breakdown response body shape
  // (routes_api_read.py) — the artifact IS dataclasses.asdict(Tokenomics(...)).
  const fixture = {
    audit_id: "aud_1",
    breakdown: {
      monthly_spend_usd: 42.5,
      tokens_in: 1000,
      tokens_out: 250,
      tokens_cached: 100,
      cache_hit_rate: 0.1,
      out_in_ratio: 0.25,
      cost_per_1k_out: 0.17,
      cost_per_request: 1.0625,
      by_model: [
        {
          name: "gpt-5.4",
          calls: 40,
          monthly_usd: 42.5,
          share: 1.0,
          cache_hit_rate: 0.1,
          out_in_ratio: 0.25,
          cost_per_1k_out: 0.17,
        },
      ],
      by_route: [
        {
          name: "chat",
          calls: 40,
          monthly_usd: 42.5,
          share: 1.0,
          cache_hit_rate: 0.1,
          out_in_ratio: 0.25,
          cost_per_1k_out: 0.17,
        },
      ],
      pct_priced: 1.0,
      pct_attributed: 1.0,
      // FR-36 behaviour lens — additive, verbatim from the artifact.
      shapes: {
        schema: 1,
        by_route: [
          {
            route: "chat",
            shape: "STEADY",
            rationale: "no loop, burst, growth or cache signal crossed its threshold across 40 calls",
          },
        ],
      },
    },
    unavailable_reason: null,
  };
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(200, fixture, (url, init) => {
      seen = { url, init };
    }),
  });
  const res = await client.getBreakdown("aud_1");
  assert.ok(seen);
  assert.match(seen.url, /\/api\/v1\/audits\/aud_1\/breakdown$/);
  assert.equal((seen.init.headers as Record<string, string>).Authorization, "Bearer rt_test");
  assert.equal(res.audit_id, "aud_1");
  assert.equal(res.unavailable_reason, null);
  assert.ok(res.breakdown);
  assert.equal(res.breakdown.monthly_spend_usd, 42.5);
  assert.equal(res.breakdown.by_model[0]?.name, "gpt-5.4");
  assert.equal(res.breakdown.by_model[0]?.monthly_usd, 42.5);
});

test("getBreakdown returns null breakdown with the unavailable_reason intact, no throw", async () => {
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(200, {
      audit_id: "aud_1",
      breakdown: null,
      unavailable_reason: "no tokenomics breakdown is available for this audit",
    }),
  });
  const res = await client.getBreakdown("aud_1");
  assert.equal(res.breakdown, null);
  assert.match(res.unavailable_reason ?? "", /no tokenomics breakdown/);
});

test("getBreakdown URL-encodes the audit id", async () => {
  let seen: { url: string; init: RequestInit } | undefined;
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(
      200,
      { audit_id: "aud/1 x", breakdown: null, unavailable_reason: "no tokenomics breakdown is available" },
      (url, init) => {
        seen = { url, init };
      },
    ),
  });
  await client.getBreakdown("aud/1 x");
  assert.ok(seen);
  assert.match(seen.url, /\/api\/v1\/audits\/aud%2F1%20x\/breakdown$/);
});

test("getBreakdown without a readToken throws before any fetch call", async () => {
  let called = false;
  const client = new TokenOps({
    fetch: mockFetch(200, {}, () => {
      called = true;
    }),
  });
  await assert.rejects(() => client.getBreakdown("aud_1"), /readToken/);
  assert.equal(called, false);
});

test("getBreakdown on a 404 raises TokenOpsError with .status === 404", async () => {
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(404, { error: { message: "audit not found" } }),
  });
  await assert.rejects(
    () => client.getBreakdown("missing"),
    (e: unknown) => e instanceof TokenOpsError && e.status === 404,
  );
});

test("a non-2xx raises TokenOpsError carrying the envelope message + status", async () => {
  const client = new TokenOps({
    readToken: "rt_test",
    fetch: mockFetch(403, { error: { message: "this token lacks the 'read:findings' scope" } }),
  });
  await assert.rejects(
    () => client.listFindings("aud_1"),
    (e: unknown) => e instanceof TokenOpsError && e.status === 403 && /read:findings/.test(e.message),
  );
});

test("calling a capability without its credential throws before any request", async () => {
  const readOnly = new TokenOps({ readToken: "rt_only" });
  await assert.rejects(() => readOnly.ingest([]), /ingestKey/);
  const writeOnly = new TokenOps({ ingestKey: "ik_only" });
  await assert.rejects(() => writeOnly.listAudits(), /readToken/);
});
