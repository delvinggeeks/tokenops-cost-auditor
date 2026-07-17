# Worked example

Our test suite audits an engineered fixture — the "waste pack" — that plants
exactly one specimen of each waste class in ~3 days of synthetic traffic. The
suite pins each finding to a hand-derived dollar figure; if the engine ever
computes a different number, the build fails. These are those numbers, with
the arithmetic. <!-- src: tests/fixtures/pricing_golden_NOTES.md; tests/test_rules.py -->

Every derivation below was computed independently of the engine (spreadsheet
`Decimal` arithmetic first, engine second) and founder-verified on
2026-07-17 against the provider rate pages.
<!-- src: pricing_golden_NOTES.md founder verification log -->

The fixture spans exactly 3 UTC days, so monthly = observed × 10.

## D2 — missing cache: $0.246784/mo

30 uncached `claude-sonnet-5` calls, identical 5,400-char prefix, 2,000 prompt
tokens, 130s apart. Intro rates: input $2, read $0.20, write $2.50; TTL 300s.

```text
cache windows = 13  →  13 writes, 17 cached reads
cacheable     = min(2000, 1024) = 1024 (hash-verified cap)
gross         = 17 × 1024 × 1.80 / 1e6 = 0.0313344
write penalty = 13 × 1024 × 0.50 / 1e6 = 0.0066560
observed      = 0.0246784  →  monthly 0.246784
```

## D4 — retry storm: $0.0510/mo

5 identical `gpt-5.4-mini` calls 20s apart (500 prompt / 200 completion):

```text
per call = (500 × 0.75 + 200 × 4.50) / 1e6 = 0.001275
wasted   = 4 × 0.001275 = 0.0051  →  monthly 0.0510
```

## D1 — oversized model: $1.35/mo

25 `claude-opus-4-8` tag-extraction calls (1,500 prompt / 60 completion),
downgrade `claude-sonnet-5`:

```text
0.009 − 0.0036 = 0.0054 per call × 25 = 0.135  →  monthly 1.35
```

## D3 — prompt bloat: $0.50/mo

Bloated route: 20 calls at 6,000 prompt tokens vs corpus bin median 1,000:

```text
excess 100,000 tokens × $1 input × 0.5 factor / 1e6 = 0.05  →  monthly 0.50
```

## D5 — unbounded max_tokens: $0.00 (informational)

12 calls declaring 8,192 max_tokens against completion p95 of 120. Flagged
(8192 ≥ 4 × 120); impact $0.00 because no reserved billing applies — the
report refuses to invent a number.

## D6 — chatty agent loop: $0.096/mo

10-call run, 65s spacing, 80-token completions, 6/10 calls sharing a prefix:

```text
saved_calls 8 × overhead 1200 × $1 / 1e6 = 0.0096  →  monthly 0.096
```

## The false-positive guard

The same suite audits a `clean_optimal` fixture — traffic engineered to be
efficient — and asserts **zero findings**. A detector that fires on clean
traffic fails the build. Precision is tested, not assumed.
<!-- src: tests/test_rules.py clean_optimal guards -->
