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
| TRACKED GAP: OpenAI cache-write counts | OpenAI response usage exposes cache READS only; the GPT-5.6 write premium engages when logs supply a wrapper-level cache_write_tokens field or via the generic CSV contract. Native OpenAI JSONL without that field under-counts 5.6 write spend (keeps estimates conservative floors). Revisit when OpenAI exposes a write-count usage field. | openai_jsonl.py (G2 re-run finding 1) |
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
 "gpt-5.6-sol":          (D("5"),    D("30"),  D("0.50"),  D("6.25")),   # C1: 1.25x input
 "gpt-5.6-luna":         (D("1"),    D("6"),   D("0.10"),  D("1.25")),   # C1: 1.25x input
 "gpt-5.4-mini":         (D("0.75"), D("4.5"), D("0.075"), D("0.75")),
 "gpt-5.4-nano":         (D("0.20"), D("1.25"),D("0.02"),  D("0.20")),
 "gpt-5.3-codex":        (D("1.75"), D("14"),  D("0.175"), D("1.75")),
}
def cost(card, p, c, w, o):
    i, out, cr, cw = R[card]
    return (max(p-c-w,0)*i + c*cr + w*cw + o*out) / D(1_000_000)
```

## waste_pack v1 golden derivations (D4 milestone; independent computation)

Fixture: waste_pack_anthropic.jsonl + waste_pack_openai.jsonl (split per file-level
format detection; tests concat the two priced frames). Combined frame spans exactly
3 distinct UTC days (2026-06-10..12) -> monthly factor 30/3 = 10.

**D2 block** (30 uncached claude-sonnet-5 calls, identical 5400-char prefix, prompt
2000, spaced 130s from 2026-06-10T09:00:00Z; intro rates input 2 / read 0.20 /
write 2.50; TTL 300s):
- windows = |{floor(epoch/300)}| = 13 -> est_writes 13, reads 17
- cacheable = min(2000, 4096//4) = 1024 (hash-verified prefix cap, R-Q5/R-Q6)
- gross = 17 x 1024 x (2 - 0.20) / 1e6 = 0.0313344
- penalty = 13 x 1024 x (2.50 - 2) / 1e6 = 0.006656
- savings_obs = 0.0246784 -> **monthly = 0.246784** (severity low, conservative)

**D4 block** (5 identical gpt-5.4-mini calls, 20s apart, prompt 500/completion 200):
- per-call cost = (500 x 0.75 + 200 x 4.5)/1e6 = 0.001275
- one cluster n=5 -> wasted_obs = 4 x 0.001275 = 0.0051 -> **monthly = 0.0510**
  (severity med: largest cluster < 10; confidence conservative, hash identity)

Severity thresholds for impact-scaled detectors: high >= $500/mo, med >= $50/mo
(findings.py; D4 uses the LLD cluster>=10 rule instead).

## waste_pack v2 golden derivations (D5 milestone; independent computation)

Frame still spans exactly 3 UTC days -> monthly factor 10. D2 block completion
raised 100->200 and max_tokens 1024->256 (isolates D1/D5 from the D2 route; D2's
own golden is prompt/cache-based and UNCHANGED at 0.246784; D4 unchanged 0.0510).

**D1 block** (25 opus-4-8 calls, tag extraction, prompt 1500 uncached, completion
60 < 150 p50; downgrade per R-D1-MAP -> sonnet-5 at June intro rates):
- per-call: opus (1500x5 + 60x25)/1e6 = 0.009; sonnet-5 (1500x2 + 60x10)/1e6 = 0.0036
- savings_obs = 25 x 0.0054 = 0.135 -> **monthly = 1.35** (estimated; caveat R-D1-MAP e)

**D3 blocks** (same completion bin 8 [256..511]: lean 40x prompt 1000 + bloated
20x prompt 6000 + filler 20x800 -> corpus bin median = 1000; bloated route p90
6000 > 2.0 x 1000):
- excess = 20 x (6000-1000) = 100000 tokens; haiku input rate 1
- savings_obs = 100000 x 1 x 0.5 / 1e6 = 0.05 -> **monthly = 0.50**

**D5 block** (12 gpt-5.6-luna calls declaring max_tokens 8192, completion p95 120;
8192 >= 4 x 120): informational finding, **monthly = 0.00** (D5_RESERVED_BILLING
false), severity low.

**D6 block** (12 haiku calls 65s apart, completion 80 < 300; run anchor 600s ->
run1 n=10 (span 585s), run2 n=2 silent; even-index calls share one prefix ->
re-read signature 6 >= 5, "agent loop suspected"):
- saved = 10 - ceil(10/5) = 8; overhead = run-median prompt = 1200; haiku input 1
- savings_obs = 8 x 1200 x 1 / 1e6 = 0.0096 -> **monthly = 0.096**

### New money-math defaults of record (D5 milestone)

| Default | Value | Where |
|---|---|---|
| D1 savings method | re-price bucket rows at suggested model's four-rate card; difference = savings (linear, equals LLD "token means x rate delta"); cached buckets excluded ("no cached reasoning marker") | d1_oversized_model.py, R-D1-MAP c |
| D1 caveat | every D1 finding carries "model suitability requires your own quality evaluation" | R-D1-MAP e |
| D3 excess definition | sum over flagged-route rows of max(prompt - corpus bin median, 0); x input rate x 0.5 safety factor (LLD) | d3_prompt_bloat.py |
| D6 overhead tokens | run-median prompt_tokens (context re-sent per call); saved calls = n - ceil(n/BATCH_SZ) | d6_chatty_loop.py |
| Model-key matching (pricing + D1 map) | exact, or key + "-2..." dated-snapshot suffix, longest key wins — prevents sibling bleed (gpt-5.4-nano never takes gpt-5.4's card) | table.py, d1_oversized_model.py |
| D4 eligibility (UAT-1 dogfood fix, D11) | cache-active rows (cached_tokens>0 OR cache_write_tokens>0) excluded — agent-session continuations are not blind retries; no-hash fingerprint = (prompt_tokens, completion_tokens), was prompt-only. Estimator formula (n-1)×mean UNCHANGED; D4 golden 0.0510 unaffected (retry block: hashes present, no cache fields) — suite re-verified green same commit | d4_retry_storm.py |
| D3/D6 effective prompt rate (UAT-1 dogfood fix, D11) | prompt-token savings priced AS BILLED: effective_rate = (uncached×input + cached×cache_read + writes×cache_write)/prompt_tokens; was flat input rate, which inflated cache-heavy agent traffic ~10× (dogfood: $46,020/mo "savings" on $20,172/mo spend, 228%). Uncached rows reduce to input rate EXACTLY → D3 golden 0.50 and D6 golden 0.096 unaffected (waste_pack blocks are uncached) — suite re-verified green same commit. Spreadsheet check: cache-heavy row 28000pt/27000 cached on haiku ⇒ blend (1000×1.00+27000×0.10)/28000 = 0.1321 $/Mtok vs input 1.00 | findings.py effective_prompt_rate, d3_prompt_bloat.py, d6_chatty_loop.py |
| Report savings cap (UAT-1 dogfood fix, D11) | headline monthly_savings = min(Σ findings, monthly_spend); optimized ≥ 0; disclosed in METHODOLOGY ("waste classes can overlap"). Per-finding numbers stay independent estimates | report/model.py |
| D5 impact | 0.0 (informational) unless D5_RESERVED_BILLING; flag at declared p50 >= 4x completion p95 | d5_unbounded_max_tokens.py |

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
- 2026-07-17 | Founder review: D4/D5 golden derivations accepted;
  detector-level values approved as engineered-fixture ground truth.
  | Lokesh Prasanna Kumar S
