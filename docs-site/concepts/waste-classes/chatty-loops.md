# D6 — Chatty agent loops

## The problem

Agent frameworks love small steps: observe, think, call a tool, repeat. Each
step re-sends the whole conversation context. Ten 80-token answers in a
burst, each carrying 1,200 tokens of re-sent context, is the signature of an
agent doing one task's work at ten tasks' input cost. This is the
agent-fleet waste class — the reason coding-agent bills surprise people.
<!-- src: R-ICP agent-fleet focus -->

## Detection

Calls are grouped into runs: same route, short completions (under 300 tokens),
consecutive calls within a 600-second anchor of each other. A run is flagged
as an agent loop when it is long enough (n ≥ some minimum) and shows the
re-read signature — a majority of the run's calls sharing one prompt prefix,
proving the same context is being re-sent. Runs too short to matter are kept
silent. <!-- src: docs/03 §3 D6; run/re-read signature -->

## Savings estimate

The estimate models batching the loop's steps (default batch factor 5) and
charges the re-sent context for the calls batching would eliminate, at the
run's *minimum* observed rate — never an average that a cheap outlier could
inflate:

```text
saved_calls = n − ceil(n / 5)
overhead    = run-median prompt tokens        (the re-sent context)
savings     = saved_calls × overhead × min input rate in the run
```
<!-- src: pricing_golden_NOTES.md D6 defaults; G3 fix: run-minimum rate -->

## Worked example (golden fixture)

12 `claude-haiku-4-5` calls 65 seconds apart, 80-token completions; run
clustering yields one 10-call run (span 585s) plus a 2-call run kept silent.
Six of the ten calls share one prefix — re-read signature met, "agent loop
suspected":

```text
saved_calls = 10 − ceil(10/5) = 8
overhead    = 1200 tokens (run-median prompt)
savings     = 8 × 1200 × $1 / 1e6 = $0.0096   →  monthly (×10) = $0.096
```
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v2 D6 -->

## Known limitations

Batching is an engineering change, not a config flag — the estimate tells you
what the loop's chattiness costs, not that a 5× batch is free to implement.
Runs without prefix evidence (no hashes in the export) fall back to timing
heuristics and are labeled at lower confidence.
