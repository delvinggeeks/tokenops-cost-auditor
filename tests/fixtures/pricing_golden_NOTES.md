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
| cache_write rate semantics | Anthropic: 5-minute-TTL write rate; OpenAI GPT-5.6 family: 1.25x input, 30-min minimum cache life (founder correction C1); other OpenAI families: no write premium → cache_write = input rate | prices.yaml, R-Q4 |
| D2 est_writes TTL windows | Per provider-family (founder correction C4): anthropic 300s, gpt-5.6 family 1800s, fallback 300s | config D2_TTL_WINDOWS |
| Surcharges NOT modeled in v1 | OpenAI long-context (>272K: 2x input / 1.5x output); regional data-residency multipliers (OpenAI post-Mar-2026 +10%, Anthropic US-only 1.1x). Spend estimates are therefore conservative FLOORS — stated in the report methodology appendix (D7). | founder correction C3 |
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
 "gpt-5.6-terra":        (D("2.5"),  D("15"),  D("0.25"),  D("3.125")),  # C1: 1.25x input
 "gpt-5.4-mini":         (D("0.75"), D("4.5"), D("0.075"), D("0.75")),
 "gpt-5.4-nano":         (D("0.20"), D("1.25"),D("0.02"),  D("0.20")),
 "gpt-5.3-codex":        (D("1.75"), D("14"),  D("0.175"), D("1.75")),
}
def cost(card, p, c, w, o):
    i, out, cr, cw = R[card]
    return (max(p-c-w,0)*i + c*cr + w*cw + o*out) / D(1_000_000)
```

## Founder verification log

- 2026-07-17 | Founder verification: all 12 rows arithmetic-recomputed
  independently (PASS). Rates cross-checked against provider pricing
  coverage same-day: Anthropic rows G01-G07,G12 confirmed incl. Sonnet-5
  intro->standard boundary (Aug31/Sep1) and 1.25x 5-min cache-write.
  OpenAI rows G08-G10 confirmed. G11 (gpt-5.3-codex) arithmetic PASS,
  rate plausible but not directly confirmed - source_url re-check
  required. | Lokesh Prasanna Kumar S
- 2026-07-17 (corrections applied): (C1) GPT-5.6 family cache_write = 1.25x input
  (sol 6.25 / terra 3.125 / luna 1.25), 30-min minimum cache life; G13 added
  exercising the terra write premium (independently computed 0.05875). Official
  page's cache-writes column re-confirmed same day. Zero-write-premium default now
  applies ONLY to GPT-5.5/5.4/5.3 families. (C2) gpt-5.3-codex re-verified against
  source_url: explicitly listed, $1.75/$0.175/$14.00 — primary-source confidence
  retained. (C3) methodology-floors note recorded (see defaults table). (C4) D2
  est_writes TTL windows are per provider-family: anthropic 300s, gpt-5.6 1800s.
