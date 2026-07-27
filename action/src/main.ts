/**
 * TokenOps Cost Auditor — GitHub Action.
 *
 * In a CI job, fetch your latest completed audit's findings (read-only, via a read
 * token) and write a ranked spend summary to the GitHub job summary — optionally
 * failing the job when a finding at/above a severity threshold exists.
 *
 * Dependency-free: platform `fetch` (Node 20) + `fs` for the step summary. Read-only,
 * observe-only — X-01/X-02 safe. Never sends prompt/completion text (FR-22).
 */

import { appendFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DEFAULT_BASE_URL = "https://tokenops-cost-auditor.com";
const SEVERITY_RANK: Record<string, number> = { low: 1, medium: 2, high: 3 };

interface Audit {
  id: string;
  status: string;
  [key: string]: unknown;
}
interface Finding {
  detector: string;
  severity: string;
  monthly_cost_impact_usd: number;
  fix: string;
  [key: string]: unknown;
}

/** Injectable so the whole run is testable without real env/network/fs. */
export interface RunDeps {
  env: NodeJS.ProcessEnv;
  fetch: typeof fetch;
  writeSummary: (markdown: string) => void;
  fail: (message: string) => void;
}

function defaultDeps(): RunDeps {
  return {
    env: process.env,
    fetch: globalThis.fetch,
    writeSummary: (md) => {
      const path = process.env.GITHUB_STEP_SUMMARY;
      if (path) appendFileSync(path, md + "\n");
      else process.stdout.write(md + "\n");
    },
    fail: (message) => {
      process.stdout.write(`::error::${message}\n`);
      process.exitCode = 1;
    },
  };
}

/** GitHub passes `inputs.read-token` as env `INPUT_READ-TOKEN` (uppercased). */
function input(env: NodeJS.ProcessEnv, name: string): string {
  return (env[`INPUT_${name.toUpperCase()}`] ?? "").trim();
}

async function api<T>(fetchImpl: typeof fetch, baseUrl: string, token: string, path: string): Promise<T> {
  const resp = await fetchImpl(`${baseUrl}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  const text = await resp.text();
  if (!resp.ok) {
    let detail = text;
    try {
      const j = JSON.parse(text) as { error?: { message?: string } };
      if (j.error?.message) detail = j.error.message;
    } catch {
      /* keep raw text */
    }
    throw new Error(`TokenOps API ${resp.status}: ${detail}`);
  }
  return JSON.parse(text) as T;
}

export async function run(deps: RunDeps = defaultDeps()): Promise<void> {
  const token = input(deps.env, "read-token");
  if (!token) return deps.fail("read-token is required (a rt_… read token with read:audits + read:findings)");
  const baseUrl = (input(deps.env, "base-url") || DEFAULT_BASE_URL).replace(/\/+$/, "");
  const failOn = input(deps.env, "fail-on-severity").toLowerCase(); // "" | low | medium | high

  let audits: Audit[];
  try {
    audits = (await api<{ audits: Audit[] }>(deps.fetch, baseUrl, token, "/api/v1/audits")).audits;
  } catch (e) {
    return deps.fail((e as Error).message);
  }
  const latest = audits.find((a) => a.status === "done");
  if (!latest) {
    deps.writeSummary("### TokenOps Cost Auditor\n\nNo completed audit found yet.");
    return;
  }

  const findings = (
    await api<{ findings: Finding[] }>(deps.fetch, baseUrl, token, `/api/v1/audits/${latest.id}/findings`)
  ).findings;
  const ranked = [...findings].sort((a, b) => b.monthly_cost_impact_usd - a.monthly_cost_impact_usd);
  const total = ranked.reduce((s, f) => s + f.monthly_cost_impact_usd, 0);
  const rows = ranked
    .map((f) => `| ${f.detector} | ${f.severity} | $${f.monthly_cost_impact_usd.toFixed(2)}/mo | ${f.fix} |`)
    .join("\n");
  deps.writeSummary(
    `### TokenOps Cost Auditor — audit \`${latest.id}\`\n\n` +
      `**${ranked.length} findings · ~$${total.toFixed(2)}/mo potential savings**\n\n` +
      (ranked.length ? `| Detector | Severity | Impact | Fix |\n|---|---|---|---|\n${rows}` : "No findings — clean run."),
  );

  if (failOn && SEVERITY_RANK[failOn]) {
    const threshold = SEVERITY_RANK[failOn]!;
    const breach = ranked.filter((f) => (SEVERITY_RANK[f.severity.toLowerCase()] ?? 0) >= threshold);
    if (breach.length) deps.fail(`${breach.length} finding(s) at or above severity "${failOn}"`);
  }
}

// Entry point (dist/main.js) — run only when invoked directly, not when imported by a test.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  run().catch((e) => {
    process.stdout.write(`::error::${(e as Error).message}\n`);
    process.exitCode = 1;
  });
}
