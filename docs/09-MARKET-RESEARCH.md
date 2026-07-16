# Market Research — TokenOps Cost Auditor (consolidated, Jul 2026)

Sources: FinOps Foundation State of FinOps 2026; DoiT/Sapio Research
survey of 500 US/UK finance leaders (Feb 2026); Mavvrik & BenchmarkIT
State of AI Cost Management (2025); Gartner 2026 forecasts; FinOps X 2026
conference reporting; vendor landscape reviews (nOps, Amnic, Maxim,
Braintrust, Finout, FutureAGI, 2026); operator field reports.

## 1. Problem magnitude (demand-side evidence)

- 79% of enterprises experienced AI cost overruns in the past 12 months
  (DoiT/Sapio, Feb 2026). 73% of organizations report AI costs blew
  original budget planning (State of FinOps 2026).
- 80-85% of enterprises miss AI infrastructure forecasts by >25%
  (Mavvrik & BenchmarkIT).
- Even FinOps-mature organizations overran by a mean of 30.9% — the
  HIGHEST of any segment (DoiT/Sapio). Cloud-FinOps maturity does not
  transfer to AI spend: waste sits upstream in prompts/models/agents
  where finance tooling cannot see.
- Operator field reports converge on 40-60% of production token budgets
  as pure waste (oversized models, missing caching, retries, agent loops).
- Structural driver: per-token prices are collapsing while total bills
  explode — usage, agents, and hidden platform costs outrun price
  declines. Gartner: global AI spending $2.59T in 2026 (~41% of all IT
  spend); AI services cost becoming a leading competitive factor in
  software margins.

## 2. Urgency & organizational shift (who buys, why now)

- FinOps teams managing AI spend: 31% (2024) -> 63% (2025) -> 98% (2026).
  The function was handed the problem by arriving invoices.
- AI cost management is the #1 named skillset gap; 58% of practitioners
  prioritizing it over the next 12 months (State of FinOps 2026).
- 78% of FinOps teams now report to CTO/CIO (only 8% to CFO): the buyer
  is ENGINEERING leadership — matches persona P1 exactly.
- New job titles emerging: "AI Cost Engineer", "LLM FinOps Lead".
  Developer token budgets becoming standard practice (NVIDIA announced
  per-engineer token budgets at GTC 2026) — validates Phase-2 budget
  enforcement and the agentic-guardrails skin (persona P2).

## 3. Competitive landscape & the gap

- Tooling layers: gateways/proxies (LiteLLM, Portkey, Helicone, Bifrost),
  observability (Langfuse, LangSmith, Datadog, Arize, W&B), FinOps
  platforms (Amnic, CloudZero, Finout, Vantage, nOps). ALL require
  integration (SDK/proxy/tagging) before first insight.
- Practitioners explicitly told the FinOps Foundation that NO commercial
  tool yet delivers granular token+LLM+GPU monitoring at enterprise
  scale; granular AI spend monitoring is the #1 most-requested
  capability across the entire 2026 survey. Analyst framing: the
  category is roughly two years from saturation.
- Agent-cost problem structurally unsolved: agents dynamically decide
  how much work to do; last month's usage does not predict next month;
  post-billing review catches overspend only after the fact (2026
  analyses). Prevention layer = our Phase 2.
- Audit-as-a-service motion validated by market entry: AWS partner
  consultancies now sell LLM cost/selection audits claiming up to 60%
  savings — enterprise-priced, human-delivered, slow.

## 4. Our wedge, restated against evidence

Zero-integration (upload logs — no SDK, proxy, or tagging project),
deterministic prescriptive findings ranked by monthly $ impact, 48-hour
turnaround, process-and-delete privacy, self-serve price ($500 /
Rs.20,000) that enterprise-tool cost structures cannot follow
down-market. Phase 2 (budgets, loop kill-switches, per-task limits)
rides the documented industry turn toward developer token budgets.

## 5. Honest caveats

- Vendor-published surveys/blogs dominate available data; percentages
  vary by sample. Directional consensus is strong; exact figures are
  not load-bearing for decisions.
- Down-market spend (<$2K/mo) may self-serve with free tools; our floor
  is customers with >=$2K/mo spend where $500 audit ROI is obvious.
- Fast-moving space: re-run this research at the day-45 gate before
  Phase-2 commitment.

## 6. Numbers usable in marketing copy (with attribution)

"79% of enterprises overran AI budgets last year" (DoiT/Sapio 2026);
"73% blew their AI budget plan" (State of FinOps 2026); "even mature
FinOps teams overspent 31% on AI" (DoiT/Sapio 2026); "40-60% of token
spend is typically waste" (operator field reports, 2026).
