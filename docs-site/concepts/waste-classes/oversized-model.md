# D1 — Oversized model

## The problem

A frontier model answering short, mechanical requests — tag extraction,
classification, routing glue — costs a multiple of what a one-tier-down model
charges for the same job. Nobody notices, because each call is cheap; the
route as a whole is not.

## Detection

The detector flags model buckets whose median completion is short (default
threshold: under 150 tokens) while running on a model that has a documented
one-tier downgrade. The downgrade map is deliberate policy, not guesswork:
exactly one tier down, never chained, never cross-provider. Frontier models
without a ruled mapping produce an informational finding with no savings
number instead of an invented one. Cached buckets are excluded — cached
reasoning traffic is not evidence of oversizing.
<!-- src: docs/03 §3 D1; R-D1-MAP rules a-f; config d1_model_map -->

## Savings estimate

Bucket rows are re-priced at the suggested model's full four-rate card; the
difference is the savings. This is linear token math — token means × rate
delta — with no behavioral assumptions.
<!-- src: pricing_golden_NOTES.md D1 defaults of record -->

## Worked example (golden fixture)

25 `claude-opus-4-8` calls doing tag extraction: 1,500 uncached prompt tokens,
60 completion tokens each (below the 150-token short-completion threshold).
Mapped downgrade: `claude-sonnet-5` at its June 2026 introductory rates.

```text
opus per call:    (1500 × $5  + 60 × $25) / 1e6 = $0.009
sonnet per call:  (1500 × $2  + 60 × $10) / 1e6 = $0.0036
observed savings: 25 × $0.0054            = $0.135
monthly (3-day window × 10):                $1.35
```
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v2 D1 -->

Confidence is `estimated`, and every D1 finding carries this caveat verbatim:
"model suitability requires your own quality evaluation." We can prove the
price difference; only you can prove the quality equivalence.
<!-- src: R-D1-MAP e -->

## Known limitations

Savings assume the downgrade handles the workload — the report never claims
that for you. Frontier models without a founder-ruled downgrade mapping are
reported as informational only, with no dollar figure.
