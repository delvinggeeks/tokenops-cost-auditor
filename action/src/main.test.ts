import test from "node:test";
import assert from "node:assert/strict";
import { run, type RunDeps } from "./main.ts";

function makeDeps(opts: { env?: NodeJS.ProcessEnv; responses: Record<string, unknown> }): {
  d: RunDeps;
  out: string[];
  fails: string[];
} {
  const out: string[] = [];
  const fails: string[] = [];
  const { responses } = opts;
  const d: RunDeps = {
    env: opts.env ?? { "INPUT_READ-TOKEN": "rt_test" },
    fetch: (async (url: unknown) => {
      const u = String(url);
      const key = Object.keys(responses).find((k) => u.includes(k)); // findings key listed first (more specific)
      const ok = key !== undefined;
      const body = ok ? responses[key] : { error: { message: "not mocked" } };
      return new Response(JSON.stringify(body), {
        status: ok ? 200 : 404,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch,
    writeSummary: (m) => out.push(m),
    fail: (m) => fails.push(m),
  };
  return { d, out, fails };
}

test("writes a ranked findings summary for the latest done audit", async () => {
  const { d, out, fails } = makeDeps({
    responses: {
      "/api/v1/audits/aud_1/findings": {
        findings: [
          { detector: "oversized_model", severity: "high", monthly_cost_impact_usd: 20, fix: "downshift" },
          { detector: "missing_cache", severity: "low", monthly_cost_impact_usd: 5, fix: "cache" },
        ],
      },
      "/api/v1/audits": { audits: [{ id: "aud_1", status: "done" }] },
    },
  });
  await run(d);
  assert.equal(fails.length, 0);
  const text = out.join("\n");
  assert.match(text, /aud_1/);
  assert.match(text, /\$25\.00\/mo/); // total
  assert.ok(text.indexOf("oversized_model") < text.indexOf("missing_cache")); // ranked by impact
});

test("fail-on-severity=high fails when a high finding exists", async () => {
  const { d, fails } = makeDeps({
    env: { "INPUT_READ-TOKEN": "rt_test", "INPUT_FAIL-ON-SEVERITY": "high" },
    responses: {
      "/api/v1/audits/aud_1/findings": {
        findings: [{ detector: "d", severity: "high", monthly_cost_impact_usd: 9, fix: "x" }],
      },
      "/api/v1/audits": { audits: [{ id: "aud_1", status: "done" }] },
    },
  });
  await run(d);
  assert.equal(fails.length, 1);
  assert.match(fails[0]!, /high/);
});

test("missing read-token fails before any request", async () => {
  const { d, fails } = makeDeps({ env: {}, responses: {} });
  await run(d);
  assert.equal(fails.length, 1);
  assert.match(fails[0]!, /read-token/);
});
