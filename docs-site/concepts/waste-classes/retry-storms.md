# D4 — Retry storms

## The problem

A timeout fires, the client retries, the provider bills both calls. Retry
loops without idempotency guards or backoff can pay for the same request
three, five, ten times — and the bill shows nothing but normal-looking calls.

## Detection

Calls with identical prompt fingerprints (hash identity where available) on
the same model are clustered inside a tight anchor window. A cluster of n > 1
identical calls in the window is n − 1 paid duplicates.
<!-- src: docs/03 §3 D4 anchor-window clustering -->

## Savings estimate

```text
wasted = (n − 1) × mean cost of the cluster's calls
```

Duplicate detection uses only priced rows — if some calls in a cluster hit an
unpriced model, they are not imputed into the estimate.
<!-- src: G3 cold-reviewer fix: priced-rows-only imputation -->

## Worked example (golden fixture)

5 identical `gpt-5.4-mini` calls, 20 seconds apart, 500 prompt / 200
completion tokens each:

```text
per call = (500 × $0.75 + 200 × $4.50) / 1e6 = $0.001275
wasted   = 4 × $0.001275                     = $0.0051
monthly (×10)                                = $0.0510
```
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v1 D4 -->

Severity for D4 follows cluster size rather than dollars — a 10-deep retry
cluster is an incident-in-waiting even when the model is cheap.
<!-- src: docs/03 LLD cluster≥10 severity rule -->

## Known limitations

Without `request_id` or prompt hashes in your export, identity is inferred
from token-count fingerprints — legitimate identical calls (polling the same
prompt on purpose) can cluster. The report's evidence rows show you the
timestamps so you can tell a storm from a schedule.
