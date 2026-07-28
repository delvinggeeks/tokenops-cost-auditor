/**
 * Official TypeScript/JavaScript SDK for the TokenOps Cost Auditor API.
 *
 * Two credentials, two capabilities (mirrors the Python SDK's laws):
 *   - an INGEST key (`ik_…`, write-only) sends usage records;
 *   - a READ token (`rt_…`, read-only) reads audits + findings.
 *
 * FR-22 BY CONSTRUCTION: `UsageRecord` carries token COUNTS and metadata only —
 * there is no field for prompt or completion text, so a caller cannot send it.
 * The SDK never sits in the request path and never enforces (X-01/X-02 safe).
 */

export const DEFAULT_BASE_URL = "https://tokenops-cost-auditor.com";

/** One usage record — counts and metadata only, never prompt/completion text. */
export interface UsageRecord {
  /** ISO-8601 timestamp of the call, e.g. "2026-07-24T10:00:00Z". */
  ts: string;
  /** Provider, e.g. "openai" | "anthropic". */
  provider: string;
  /** Model id, e.g. "gpt-5.4". */
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  /** Cached (prompt-cache read) tokens, if any. */
  cached_tokens?: number;
}

export interface IngestResponse {
  audit_id: string;
  records: number;
  replayed: boolean;
}

export interface Audit {
  id: string;
  status: string;
  findings: number;
  [key: string]: unknown;
}

/** One audit's own summary — totals, cost, counts, scope, timing. No prompt/completion field. */
export interface AuditSummary {
  id: string;
  status: string;
  scope_label: string;
  created_at: string | null;
  completed_at: string | null;
  totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  };
  model_count: number;
  finding_count: number;
}

/** One dimension value (a model, or a route/tag) with its exact economics. */
export interface BreakdownSlice {
  name: string;
  calls: number;
  monthly_usd: number;
  share: number;
  cache_hit_rate: number;
  out_in_ratio: number;
  cost_per_1k_out: number;
}

/** FR-36 behaviour lens: one route's deterministic workload-shape classification.
 * Classified from counts, timing, model and cache fields only — never content.
 * `rationale` is a fixed template naming the exact counts that fired the class. */
export interface RouteShape {
  route: string;
  shape: "AGENT_LOOP" | "RETRY_BURST" | "CONTEXT_GROWTH" | "UNCLAIMED_CACHE" | "STEADY";
  rationale: string;
}

/** The audit's tokenomics breakdown — vitals, per-model/per-route allocation, coverage. */
export interface AuditTokenomics {
  monthly_spend_usd: number;
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  cache_hit_rate: number;
  out_in_ratio: number;
  cost_per_1k_out: number;
  cost_per_request: number;
  by_model: BreakdownSlice[];
  by_route: BreakdownSlice[];
  pct_priced: number;
  pct_attributed: number;
  /** Absent on audits that ran before the shape lens shipped (honest null —
   * the server never back-fills a classification). */
  shapes?: { schema: number; by_route: RouteShape[] };
}

/** GET /api/v1/audits/{id}/breakdown response — `breakdown` is null when unavailable. */
export interface AuditBreakdownResponse {
  audit_id: string;
  breakdown: AuditTokenomics | null;
  unavailable_reason: string | null;
}

export interface Finding {
  detector: string;
  severity: string;
  monthly_cost_impact_usd: number;
  fix: string;
  [key: string]: unknown;
}

export interface TokenOpsOptions {
  /** Ingest key (`ik_…`), write-only — required to call `ingest`. */
  ingestKey?: string;
  /** Read token (`rt_…`), read-only — required to call `listAudits` / `listFindings`. */
  readToken?: string;
  /** API origin. Defaults to the hosted instance. */
  baseUrl?: string;
  /** Injectable fetch (defaults to global fetch; pass a mock in tests). */
  fetch?: typeof fetch;
}

/** Thrown on any non-2xx API response; `.status` and `.detail` carry the envelope. */
export class TokenOpsError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`TokenOps API error ${status}: ${describe(detail)}`);
    this.name = "TokenOpsError";
    this.status = status;
    this.detail = detail;
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const err = d.error as Record<string, unknown> | undefined;
    if (err && typeof err.message === "string") return err.message; // NFR-14 envelope
    if (typeof d.detail === "string") return d.detail;
  }
  return JSON.stringify(detail);
}

export class TokenOps {
  private readonly ingestKey?: string;
  private readonly readToken?: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: TokenOpsOptions = {}) {
    this.ingestKey = opts.ingestKey;
    this.readToken = opts.readToken;
    this.baseUrl = (opts.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    const f = opts.fetch ?? globalThis.fetch;
    if (!f) {
      throw new Error("no fetch available — pass options.fetch (Node <18 has no global fetch)");
    }
    this.fetchImpl = f;
  }

  /** Send a batch of usage records (counts only). Requires an ingest key. */
  async ingest(records: UsageRecord[]): Promise<IngestResponse> {
    if (!this.ingestKey) throw new Error("ingest requires an ingestKey (ik_…)");
    return this.request<IngestResponse>("POST", "/api/v1/ingest", this.ingestKey, { records });
  }

  /** List recent audits (status, spend totals, counts). Requires a read token with `read:audits`. */
  async listAudits(): Promise<Audit[]> {
    if (!this.readToken) throw new Error("listAudits requires a readToken (rt_…)");
    const body = await this.request<{ audits: Audit[] }>("GET", "/api/v1/audits", this.readToken);
    return body.audits;
  }

  /** One audit's summary (totals, cost, counts, scope, timing). Requires `read:audits`. */
  async getAudit(auditId: string): Promise<AuditSummary> {
    if (!this.readToken) throw new Error("getAudit requires a readToken (rt_…)");
    const path = `/api/v1/audits/${encodeURIComponent(auditId)}`;
    return this.request<AuditSummary>("GET", path, this.readToken);
  }

  /**
   * The audit's tokenomics breakdown (vitals, per-model/per-route cost allocation,
   * data coverage) — the whole response, INCLUDING `unavailable_reason` (do not
   * unwrap to just `breakdown`, or a caller loses "no data, and here's why").
   * Requires `read:audits`.
   */
  async getBreakdown(auditId: string): Promise<AuditBreakdownResponse> {
    if (!this.readToken) throw new Error("getBreakdown requires a readToken (rt_…)");
    const path = `/api/v1/audits/${encodeURIComponent(auditId)}/breakdown`;
    return this.request<AuditBreakdownResponse>("GET", path, this.readToken);
  }

  /** Findings for one audit, ranked by monthly $ impact. Requires `read:findings`. */
  async listFindings(auditId: string): Promise<Finding[]> {
    if (!this.readToken) throw new Error("listFindings requires a readToken (rt_…)");
    const path = `/api/v1/audits/${encodeURIComponent(auditId)}/findings`;
    const body = await this.request<{ findings: Finding[] }>("GET", path, this.readToken);
    return body.findings;
  }

  /** Poll `listAudits` until the given audit reaches a terminal status, or time out. */
  async waitForAudit(auditId: string, opts: { timeoutMs?: number; intervalMs?: number } = {}): Promise<Audit> {
    const timeoutMs = opts.timeoutMs ?? 120_000;
    const intervalMs = opts.intervalMs ?? 3_000;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const match = (await this.listAudits()).find((a) => a.id === auditId);
      if (match && (match.status === "done" || match.status === "failed")) return match;
      await sleep(intervalMs);
    }
    throw new Error(`audit ${auditId} not finished after ${timeoutMs}ms`);
  }

  private async request<T>(method: string, path: string, token: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const resp = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await resp.text();
    const parsed = text ? safeJson(text) : undefined;
    if (!resp.ok) throw new TokenOpsError(resp.status, parsed ?? text);
    return parsed as T;
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
