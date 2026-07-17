# D2 — Missing cache

## The problem

Both major providers discount cached prompt prefixes steeply — Anthropic cache
reads cost a tenth of the input rate. If your traffic re-sends the same system
prompt or context block at the full input rate, you are paying the same bill
over and over for tokens the provider would happily serve from cache.

## Detection

The detector groups calls by identical prompt prefix (SHA-256 over the first
4,096 prompt characters when your export carries `prefix_hash`; a conservative
heuristic otherwise) and finds groups that never used cache despite repeating
within the provider's cache lifetime.
<!-- src: docs/03 §3 D2; R-Q5 cacheable definition -->

## Savings estimate

The estimate is a full cache simulation, not a flat discount:

```text
cacheable    = hash-verified: min(prompt_tokens, 1024-token cap)
               heuristic:     0.8 × group-minimum prompt
est_writes   = number of cache-lifetime windows the group spans
               (one write per window; TTL is provider-family specific)
gross        = reads × cacheable × (input_rate − cache_read_rate) / 1e6
penalty      = est_writes × cacheable × (cache_write_rate − input_rate) / 1e6
savings      = gross − penalty        (0.7 haircut if windows can't be estimated)
```
<!-- src: R-Q4 formula; R-Q6 cap; C4 per-family TTL windows -->

Cache lifetimes differ per provider family — Anthropic's 5-minute TTL means
more re-writes than the GPT-5.6 family's 30-minute minimum, and the write
premium differs too (Anthropic writes at 1.25× input; the 5.6 family likewise;
older OpenAI families have no premium). The simulation uses the right window
and premium per family. <!-- src: prices.yaml C1/C4 corrections -->

## Worked example (golden fixture)

30 uncached `claude-sonnet-5` calls, identical 5,400-character prefix, 2,000
prompt tokens, spaced 130 seconds apart (intro rates: input $2, read $0.20,
write $2.50; TTL 300s):

```text
windows   = 13  →  est_writes 13, cached reads 17
cacheable = min(2000, 4096/4) = 1024 tokens (hash-verified cap)
gross     = 17 × 1024 × (2.00 − 0.20) / 1e6 = $0.0313344
penalty   = 13 × 1024 × (2.50 − 2.00) / 1e6 = $0.0066560
observed  = $0.0246784   →  monthly (×10) = $0.246784
```
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v1 D2 -->

Note what the conservatism does: a naive "cache everything" estimate would
claim the full read discount on all 30 calls; the simulation pays for 13 cache
writes first and caps cacheable tokens at the hash-verified span.

## Known limitations

OpenAI usage exports do not carry per-call cache-write counts (TRACKED GAP):
for OpenAI traffic the write penalty is estimated from TTL windows, never
observed. Anthropic exports carry both cache fields natively. If a prefix
repeats but crosses cache-lifetime boundaries slowly, real-world savings will
be lower than a same-minute burst — the window simulation models exactly this.
