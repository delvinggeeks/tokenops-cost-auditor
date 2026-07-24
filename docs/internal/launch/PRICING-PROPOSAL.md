# Pricing proposal — market-grounded (deep research, 2026-07-27)

For founder ruling. Sources: live vendor pricing pages fetched 2026-07-21 and
adversarially verified (3-vote); full citations in the research run
(wf_19efbefc-b06). Nothing below changes the price config until ruled.

## Where the market sits (verified)

| Tool | Entry | Mid | Team/Ent | Model |
|---|---|---|---|---|
| Langfuse | $29 Core | $199 Pro | $2,499 Ent | flat + $8/100k-unit overage |
| Helicone | $79 Pro (unlim. seats) | — | $799 Team | flat, feature-gated |
| Portkey | $49 (100k logs) | — | custom @10M+ | flat + $9/100k overage |
| Vantage (FinOps) | $30/mo per $7.5K spend | $200/mo per $20K | ~1% of spend | % of managed spend |
| Finout | — | — | ~$1,000/mo per $500K/yr | ~2.4% of spend at cap |
| Legacy (Cloudability etc.) | — | — | 2–3% of spend | % of managed spend |

Success-fee precedent: Vantage Autopilot = 5% of realized savings ("if you
don't save, we don't charge"); Usage.ai = pure % of verified savings.
Freemium→paid norms: 3–5% (8–12% is exceptional). Buyer segments by monthly
LLM spend: <$30K / $30K–$200K / >$200K; AI tooling runs $200–600/dev/mo and
enterprise LLM budgets are growing ~75% YoY.

## The verdict on current pricing

**$99 Pro and $299 Scale are already "ultra realistic":** $99 = 1–3% of
$3.3K–$10K monthly audited AI spend; $299 = 1–3% of $10K–$30K — squarely the
FinOps price-to-managed-spend norm, and bracketed by Langfuse Pro ($199) and
Helicone Team ($799). The problem was never the number; it was that nothing
on the page ANCHORED it. Underpricing signals toy; these numbers don't.

## Three defensible structures (ruling options)

**A — RECOMMENDED. Keep $99/$299 flat; add explicit audited-spend gates.**
Pro covers up to ~$10K/mo audited AI spend; Scale up to ~$50K; above that,
enterprise at ~1% of audited spend (talk-to-us line). One sentence on the
plans section does the anchoring: "Pro pays for itself against ~$10K of
monthly AI spend — the industry norm is 1–3% of managed spend." Zero config
changes, zero metering complexity, honest growth path.

**B — Flat base + metered overage** (Langfuse/Portkey grammar): $99 includes
N audited calls/mo, overage per 100k. Defers nothing, adds metering,
billing complexity now for revenue later. Not recommended pre-launch.

**C — Success fee on verification** (Vantage Autopilot/Usage.ai grammar):
keep subscriptions; convert the $500 enterprise one-shot to "$500 minimum or
10–15% of VERIFIED first-quarter savings, whichever is greater." Directly
monetizes our differentiator (the verified-only headline). Recommended as a
LATER experiment on the enterprise line only — it needs contract language
(Terms addition) and a quarter of verification history to invoice against.

## Ruling requested

Reply with one of: "PRICING A" (spend-gates + anchor line ship with the next
deploy), "PRICING B", "PRICING C", or amendments by letter. Until then the
price config is untouched.
