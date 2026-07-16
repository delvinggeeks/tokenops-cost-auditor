# pricing_golden — notes sheet

This is the "notes sheet" required by founder ruling R-Q6..Q12(a): every default
that touches money math is recorded here. Golden values in pricing_golden.csv were
computed INDEPENDENTLY of the code under test (plain Decimal arithmetic from the
provider rate cards — generator preserved verbatim below) and must be hand-verified
by the founder against provider pricing pages BEFORE gate sweep G2 runs (R-Q3).

## Rate sources (fetched 2026-07-17)

- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
  (exact table incl. 5m/1h cache-write and cache-read columns; Sonnet 5
  introductory pricing $2/$10 through 2026-08-31, standard $3/$15 from 2026-09-01)
- OpenAI: https://developers.openai.com/api/docs/pricing
  (cached input bills at 10% of input; no separate cache-write charge)

## Money-math defaults of record

| Default | Value | Where |
|---|---|---|
| cache_write rate semantics | Anthropic 5-minute-TTL write rate (matches D2_TTL_WINDOW_S=300); OpenAI: no write premium → cache_write = input rate | prices.yaml, R-Q4 |
| Token semantics | prompt_tokens = TOTAL input (Anthropic input+cache_read+cache_creation unified by normalizer); cached_tokens = cache READ subset; cache_write_tokens = Anthropic cache_creation | normalizer.py, R-Q4 |
| Per-call cost formula | (max(prompt−cached−write,0)·input + cached·cache_read + write·cache_write + completion·output)/1e6 | coster.py |
| Negative-uncached guard | clip at 0 (malformed rows cannot produce negative cost) | coster.py |
| Reconciliation tolerance | ±0.5% (NFR-07) | coster.py |
| Unknown model | PricingGapError → cost NaN, audit continues, model listed in report | table.py/coster.py |
| effective_from policy | provider-published date where available; else 2026-06-01 = "verified current at fetch, coverage opened for 30-day logs" — FOUNDER TO ADJUST | prices.yaml |
| Monthly extrapolation (D4+ detectors) | observed waste × 30/observed_days, observed_days = span of distinct UTC days, min 1 (accepted Q7) | rules (D4-D5 milestone) |
| D2 est_writes haircut | 0.7 when TTL windows cannot be estimated (R-Q4) | rules (D4 milestone) |
| D2 cacheable haircut | 0.8 × min(prompt_tokens in bucket) without hash evidence (R-Q5) | rules (D4 milestone) |
| prefix_hash length | SHA-256 over first 4096 chars ≈ 1024 tokens (R-Q6) | normalizer.py |
| D3 bloat binning | log2 buckets on completion_tokens (accepted Q10) | rules (D5 milestone) |
| D6 batch size | D6_BATCH_SZ = 5 (accepted default) | config.py |

## Independent generator (verbatim; run with plain python, no project imports)

```python
from decimal import Decimal as D
R = {  # input, output, cache_read, cache_write (USD/MTok)
 "claude-opus-4-8":      (D("5"),    D("25"),  D("0.50"),  D("6.25")),
 "claude-sonnet-5-intro":(D("2"),    D("10"),  D("0.20"),  D("2.50")),
 "claude-sonnet-5-std":  (D("3"),    D("15"),  D("0.30"),  D("3.75")),
 "claude-haiku-4-5":     (D("1"),    D("5"),   D("0.10"),  D("1.25")),
 "claude-fable-5":       (D("10"),   D("50"),  D("1.00"),  D("12.50")),
 "gpt-5.6-terra":        (D("2.5"),  D("15"),  D("0.25"),  D("2.5")),
 "gpt-5.4-mini":         (D("0.75"), D("4.5"), D("0.075"), D("0.75")),
 "gpt-5.4-nano":         (D("0.20"), D("1.25"),D("0.02"),  D("0.20")),
 "gpt-5.3-codex":        (D("1.75"), D("14"),  D("0.175"), D("1.75")),
}
def cost(card, p, c, w, o):
    i, out, cr, cw = R[card]
    return (max(p-c-w,0)*i + c*cr + w*cw + o*out) / D(1_000_000)
```

## Founder verification log

- (pending) 8–10 rows hand-verified against provider pricing pages: ____________
