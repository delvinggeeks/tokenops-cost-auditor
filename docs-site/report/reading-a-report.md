# Reading a report

Every report — web, PDF, JSON — renders from one assembled model, so the three
artifacts never disagree. This page walks the sections in reading order.
<!-- src: docs/03 ADR-4; T-REP-01 -->

## Header and executive summary

The header states the audit id, generation date, observed window (days of
traffic), and call count. The summary leads with one number: **estimated
monthly savings**, with the percentage of current spend it represents. Around
it, four cards: current monthly spend (your observed window scaled to 30
days), the optimized projection, raw observed spend, and the findings count.
<!-- src: FR-13; report/model.py -->

Every "monthly" figure is the observed window × 30 ÷ observed days. A 3-day
sample scales by 10 — the report says so on the card, not in a footnote.
<!-- src: R-Q7 -->

## Savings waterfall

Findings ranked by monthly dollar impact, largest first, with proportional
bars. This is the triage view: the top one or two rows usually carry most of
the recoverable spend.

## Spend charts

Observed spend by model and by UTC day — where the money went, and whether
spend is trending or spiky. Chart values are observed dollars, not
projections.

## Findings in detail

Each finding card carries:

| Field | Meaning |
|---|---|
| id | stable finding id (`D2-...`), deep-linkable |
| severity | `high` ≥ $500/mo, `med` ≥ $50/mo, else `low` (D4: cluster-based; D5: informational) |
| confidence | how the estimate was grounded — `verified` (hash evidence), `estimated`, `conservative`, `informational` |
| monthly impact | the dollar estimate, computed per the class formula |
| fix | the concrete change we recommend |
| evidence | up to 20 sample calls: timestamp, model, token counts, note — never text |

<!-- src: FR-09/10/14; services/rules/findings.py -->

## Pricing provenance

The report states the pricing-table version and human-verification date used
to price it, and lists any unpriced models excluded from totals — count and
ids, so you know exactly what the totals do not include.
<!-- src: FR-28; NFR-15 -->

## Methodology and data handling

The final sections print the methodology statement (every haircut and
conservatism disclosed) and the data-handling policy — the same text on every
report, so the report is self-explaining when forwarded to finance.
<!-- src: report/model.py METHODOLOGY, DATA_HANDLING constants -->

## The JSON artifact

`report.json` carries the same model: audit metadata, totals, spend
breakdowns, findings with evidence. It is deterministic — the same upload
produces byte-identical JSON (`generated_at` excluded) — so you can diff two
audits of the same log and expect zero noise. <!-- src: T-REP-03/08 -->

## The enterprise breakdown: behaviour lens

The `/breakdown` dashboard page (and its read-API twin,
[`GET /audits/{id}/breakdown`](../api/reference.md)) goes one level deeper
than the report: per-model and per-route cost allocation, unit-economics
ratios, and a **workload-shape chip per route** — the behaviour lens. Each
route's calls are classified into one of five shapes — agent loop, retry
burst, context growth, unclaimed cache, or steady — from call counts, timing,
model and cache fields only, the same determinism law as the detectors above:
no content is ever read, and the one-line rationale under each chip names the
exact counts that fired it. <!-- src: FR-36; services/dashboard/shapes.py -->

The breakdown needs per-request rows, so it degrades honestly where those
aren't available: a connected usage API reports daily aggregates only, and the
page says so plainly rather than guessing a shape. An audit from before this
lens shipped simply has no shape data — never a fabricated "steady".
<!-- src: FR-36 depth honesty -->
