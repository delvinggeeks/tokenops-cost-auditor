# Pricing data

Money math is only as good as the rate card behind it. Ours is versioned,
effective-dated, and verified by a human — and the report tells you exactly
which version priced your audit. <!-- src: R-PRICING-OPS ruling; FR-28 -->

## Four rates per model

Every model carries four USD-per-million-token rates: input, output, cache
write, cache read. Modern waste analysis is impossible with a two-rate card —
cache economics (the largest waste class in agent traffic) live entirely in
the write premium and the read discount. <!-- src: R-Q4 -->

## Effective-dated, timestamp-matched

Rates carry `effective_from` dates, and each call is priced at the rate in
effect at its timestamp. When a provider changes prices mid-window — like
Sonnet 5's introductory pricing ending 2026-08-31 — a log spanning the
boundary prices each side correctly instead of smearing one rate across both.
<!-- src: FR-05; prices.yaml effective_from policy -->

Model keys match exactly, or as dated snapshots (`model-key-2...`), longest
key first — `gpt-5.4-nano` can never silently take `gpt-5.4`'s card.
<!-- src: table.py boundary rule -->

## Human-verified, on the record

The table carries a `last_verified` date. Our CI warns loudly when it exceeds
14 days; the founder's daily ops digest carries the age; and the verification
itself is logged with the verifier's name and the corrections made.
<!-- src: NFR-15; pricing_golden_NOTES.md founder verification log -->

A weekly read-only refresh script fetches the documented source pages and
prints a drift diff — new model ids, candidate rate mismatches, unreachable
pages. It **cannot write the pricing table**; by design there is no code path
from a scraped page to a rate used in money math. A human reads the diff,
verifies against the provider's page, and edits the table by hand.
<!-- src: FR-29; scripts/pricing_refresh.py -->

!!! note "Why we refuse live pricing"
    Scraped or API-fetched rates change without audit trail and break
    reproducibility: the same log re-audited next month must price identically
    unless a human recorded a rate change. A versioned file with dated rows is
    slower to update and much harder to be wrong with.

## When a model is not in the table

Calls on models without a verified rate card are excluded from totals and
listed in the report as unpriced — count and model ids — rather than priced by
guesswork. Spend reconciliation (our ±0.5% property test) runs only over
priced rows and says so. <!-- src: PricingGapError; NFR-07 -->
