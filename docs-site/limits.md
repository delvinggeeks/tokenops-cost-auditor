# Limits

What this product does not do, and where the estimates stop. No roadmap
promises here — just the current boundaries, stated plainly.
<!-- src: docs/01 §G; methodology caveats -->

## Product boundaries (by design, not omission)

- **No live proxy or gateway.** We never sit in your request path. The audit
  is offline analysis of logs you already have. (X-01)
- **No enforcement.** We report waste; we never act on your account, set
  budgets, or block calls. (X-02)
- **No multi-org RBAC or SSO.** One email, one account, magic-link sign-in.
  (X-03)
- **No AI-written report text.** Every sentence in a report is a template;
  every number is deterministic arithmetic. (X-04)
- **Plain server-rendered pages**, no SPA. (X-05)

## Methodology caveats

- **Aggregate-only exports underestimate.** If your provider export carries
  daily aggregates instead of per-call records, per-call detectors (retries,
  loops, caching) cannot run at full power; the report says which detectors
  ran degraded.
- **Unpriced models are excluded, not guessed.** Calls on models without a
  verified rate card are listed and left out of totals.
  <!-- src: PricingGapError behavior -->
- **Cache-write floors.** Cache savings subtract estimated write costs; where
  write windows cannot be estimated, a 0.7 haircut applies. These floors mean
  our cache numbers are lower than most tools' — deliberately.
  <!-- src: R-Q4; C3 floors -->
- **OpenAI cache-write counts are a tracked gap.** OpenAI usage exports do not
  carry per-call cache-write counts, so the write side of cache simulation is
  estimated from cache-lifetime windows for OpenAI traffic. Anthropic exports
  carry both fields natively. <!-- src: C3 TRACKED GAP -->
- **Downgrade savings assume quality holds.** Every oversized-model finding
  says so explicitly; we can prove the price delta, only you can prove the
  quality equivalence. <!-- src: R-D1-MAP e -->
- **Monthly figures are extrapolations** of your observed window (× 30 ÷
  observed days). Send a representative window — a quiet weekend sample will
  under-report. <!-- src: R-Q7 -->

## Operational limits

- Uploads to 200 MB per audit (larger sets: split by time range).
- One audit runs per credit; processing beyond the concurrency cap queues,
  with position visible in the status API.
- Report links expire after 30 days; raw uploads purge after 7. Download your
  PDF.
