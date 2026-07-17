# The six waste classes

Every audit checks the same six classes. Each detector is independent,
deterministic, and conservative — when a number cannot be estimated safely, the
finding says so instead of inflating it. Findings are ranked by estimated
monthly dollar impact in the report. <!-- src: FR-07..FR-12; docs/03 §3 -->

| # | Class | What it catches | Severity logic | Confidence label |
|---|---|---|---|---|
| D1 | [Oversized model](oversized-model.md) | Frontier-model calls doing work a one-tier-down model handles | impact-scaled (high ≥ $500/mo, med ≥ $50/mo) | `estimated` — carries a quality caveat |
| D2 | [Missing cache](missing-cache.md) | Repeated identical prompt prefixes paid at full input rate | impact-scaled | `verified` with prefix hashes, else `estimated` |
| D3 | [Prompt bloat](prompt-bloat.md) | Routes whose prompts are far above the corpus median for the same output size | impact-scaled | `estimated` (half-excess safety factor) |
| D4 | [Retry storms](retry-storms.md) | The same request paid for again and again inside a tight window | cluster-size based | `conservative` (hash identity) |
| D5 | [Unbounded max_tokens](unbounded-max-tokens.md) | Declared output caps wildly above actual output | informational | `informational` ($0 unless reserved billing applies) |
| D6 | [Chatty agent loops](chatty-loops.md) | Agents re-sending the same context in bursts of small calls | impact-scaled | `estimated` |

## How to read the numbers

- **Monthly impact** normalizes your observed window to 30 days
  (× 30 ÷ observed days). A 3-day log sample scales by 10.
  <!-- src: R-Q7 monthly factor -->
- **Severity** is a triage aid: `high` ≥ $500/mo, `med` ≥ $50/mo, else `low` —
  except D4, which uses retry-cluster size, and D5, which is informational.
  <!-- src: services/rules/findings.py severity_for_impact -->
- **Confidence** tells you how the estimate was grounded: hash-verified
  evidence, conservative heuristics, or informational-only.

Each class page shows the exact detection rule, the exact savings formula, a
worked example computed from our engineered test fixture (the same golden
numbers our test suite pins), and known limitations.
