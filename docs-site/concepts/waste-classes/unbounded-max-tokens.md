# D5 — Unbounded max_tokens

## The problem

Declaring `max_tokens: 8192` for calls that produce 120-token answers is
usually harmless today — you pay for produced tokens, not declared ones. It
still matters twice over: some billing modes and capacity reservations charge
against the declared cap, and an unbounded cap is a latent cost bug the first
time a prompt regression makes the model actually fill it.

## Detection

Routes are flagged when the declared cap's median is at least four times the
route's 95th-percentile actual completion.
<!-- src: docs/03 §3 D5; declared p50 ≥ 4 × completion p95 -->

## Savings estimate

Zero, by default — and the report says so. D5 is an informational finding
unless reserved-capacity billing applies to your account, because charging you
a "savings" number for tokens you never paid for would be invented money.
<!-- src: pricing_golden_NOTES.md D5 default of record -->

## Worked example (golden fixture)

12 `gpt-5.6-luna` calls declaring `max_tokens: 8192` with an actual completion
p95 of 120 tokens. 8192 ≥ 4 × 120, so the route is flagged — severity `low`,
monthly impact **$0.00**, labeled informational.
<!-- src: tests/fixtures/pricing_golden_NOTES.md waste_pack v2 D5 -->

## Known limitations

Only exports that carry `declared_max_tokens` feed this detector — most
provider-side usage exports do not include it; the generic CSV contract and
the Claude Code exporter do. If your billing includes reserved output
capacity, tell us when commissioning the audit and the finding is priced
accordingly.
