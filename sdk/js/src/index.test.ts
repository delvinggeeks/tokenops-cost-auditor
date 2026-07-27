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
