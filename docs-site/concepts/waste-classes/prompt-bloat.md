# D3 — Prompt bloat

## The problem

Prompts grow. Few shrink. RAG pipelines that stuff every retrieved chunk into
context, system prompts that accrete instructions, few-shot examples nobody
re-evaluated — the output stays the same size while the input balloons.

## Detection

Calls are grouped by route (`tag`/`endpoint`) and binned by completion size,
so comparisons are like-for-like: a route is flagged when its 90th-percentile
prompt is more than twice the corpus median prompt *for the same completion
bin*. Producing the same-sized answer from far more context than your other
routes need is the bloat signature.
<!-- src: docs/03 §3 D3 -->

## Savings estimate

```text
excess  = Σ max(prompt_tokens − corpus bin median, 0) over flagged-route rows
savings = excess × input_rate × 0.5
```

The 0.5 safety factor bakes in the assumption that only half the excess is
actually removable — some of that context is probably load-bearing.
<!-- src: pricing_golden_NOTES.md D3 default of record -->

## Worked example (golden fixture)

Same completion bin (256–511 tokens): a lean route sends 40 calls at 1,000
prompt tokens, a bloated route sends 20 calls at 6,000, filler traffic sends
20 at 800. Corpus bin median: 1,000. The bloated route's p90 (6,000) exceeds
2 × 1,000 — flagged.

```text
excess  = 20 × (6000 − 1000) = 100,000 tokens
savings = 100,000 × $1 (haiku input) × 0.5 / 1e6 = $0.05
monthly (×10)                                    = $0.50
```
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v2 D3 -->

## Known limitations

The detector reasons about token counts, never content — it cannot tell you
*which* part of the prompt is removable, only that the route is a statistical
outlier against your own traffic. Routes with genuinely unique context needs
can exceed the threshold legitimately; the 0.5 factor and the like-for-like
binning exist to keep such findings honest.
