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
const SEVERITY_RANK = { low: 1, medium: 2, high: 3 };
function defaultDeps() {
    return {
        env: process.env,
        fetch: globalThis.fetch,
        writeSummary: (md) => {
            const path = process.env.GITHUB_STEP_SUMMARY;
            if (path)
                appendFileSync(path, md + "\n");
            else
                process.stdout.write(md + "\n");
        },
        fail: (message) => {
            process.stdout.write(`::error::${message}\n`);
            process.exitCode = 1;
        },
    };
}
/** GitHub passes `inputs.read-token` as env `INPUT_READ-TOKEN` (uppercased). */
function input(env, name) {
    return (env[`INPUT_${name.toUpperCase()}`] ?? "").trim();
}
async function api(fetchImpl, baseUrl, token, path) {
    const resp = await fetchImpl(`${baseUrl}${path}`, { headers: { Authorization: `Bearer ${token}` } });
    const text = await resp.text();
    if (!resp.ok) {
        let detail = text;
        try {
            const j = JSON.parse(text);
            if (j.error?.message)
                detail = j.error.message;
        }
        catch {
            /* keep raw text */
        }
        throw new Error(`TokenOps API ${resp.status}: ${detail}`);
    }
    return JSON.parse(text);
}
export async function run(deps = defaultDeps()) {
    const token = input(deps.env, "read-token");
    if (!token)
        return deps.fail("read-token is required (a rt_… read token with read:audits + read:findings)");
    const baseUrl = (input(deps.env, "base-url") || DEFAULT_BASE_URL).replace(/\/+$/, "");
    const failOn = input(deps.env, "fail-on-severity").toLowerCase(); // "" | low | medium | high
    let audits;
    try {
        audits = (await api(deps.fetch, baseUrl, token, "/api/v1/audits")).audits;
    }
    catch (e) {
        return deps.fail(e.message);
    }
    const latest = audits.find((a) => a.status === "done");
    if (!latest) {
        deps.writeSummary("### TokenOps Cost Auditor\n\nNo completed audit found yet.");
        return;
    }
    const findings = (await api(deps.fetch, baseUrl, token, `/api/v1/audits/${latest.id}/findings`)).findings;
    const ranked = [...findings].sort((a, b) => b.monthly_cost_impact_usd - a.monthly_cost_impact_usd);
    const total = ranked.reduce((s, f) => s + f.monthly_cost_impact_usd, 0);
    const rows = ranked
        .map((f) => `| ${f.detector} | ${f.severity} | $${f.monthly_cost_impact_usd.toFixed(2)}/mo | ${f.fix} |`)
        .join("\n");
    deps.writeSummary(`### TokenOps Cost Auditor — audit \`${latest.id}\`\n\n` +
        `**${ranked.length} findings · ~$${total.toFixed(2)}/mo potential savings**\n\n` +
        (ranked.length ? `| Detector | Severity | Impact | Fix |\n|---|---|---|---|\n${rows}` : "No findings — clean run."));
    if (failOn && SEVERITY_RANK[failOn]) {
        const threshold = SEVERITY_RANK[failOn];
        const breach = ranked.filter((f) => (SEVERITY_RANK[f.severity.toLowerCase()] ?? 0) >= threshold);
        if (breach.length)
            deps.fail(`${breach.length} finding(s) at or above severity "${failOn}"`);
    }
}
// Entry point (dist/main.js) — run only when invoked directly, not when imported by a test.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
    run().catch((e) => {
        process.stdout.write(`::error::${e.message}\n`);
        process.exitCode = 1;
    });
}
