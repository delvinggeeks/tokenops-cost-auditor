# India pricing analysis — founder amendment to R-PRICING-FINAL (2026-07-21)

Founder instinct under test: "Indian prices have to be ~₹1,000–2,000 or no
individual will pay; and the product must live in their ecosystem every day
or nobody pays for a one-time job." Three research passes (verified, sourced;
agents a1e66ed/a876ee8/a31d306, 2026-07-21) ground this.

## 1. What the Indian market actually pays (verified)

**AI subscriptions in India:**
| Product | India price | Global | Ratio |
|---|---|---|---|
| ChatGPT Go (India-first tier) | ₹399/mo | $8 | 0.57 |
| Google AI Plus | ₹399/mo | $7.99 | 0.57 |
| ChatGPT Plus | ₹1,999/mo | $20 | ~1.1 |
| Claude Pro | ~₹2,399/mo incl. GST | $20 | ~1.2–1.4 |
| Gemini AI Pro | ₹1,950/mo | $19.99 | ~1.1 |
| GitHub Copilot / Cursor | USD-billed, no India price | $10 / $20 | 1.0 |

**PPP norms:** consumer media 0.12–0.30 (YouTube Premium ₹149, Netflix);
deliberate India-first AI tiers cluster at ~0.57; B2B SaaS guidance: India at
40–60% of US sticker. **Indian SaaS entry band: ₹800–1,500/user/mo** (Zoho
CRM ₹800, Freshsales ₹1,099, Zoho One ₹1,250–1,500).

**Payment rails:** RBI e-mandate framework 2026 confirms the ₹15,000 AFA
exemption — ₹14,999 auto-debits frictionlessly, ₹15,001 needs OTP every
cycle. UPI Autopay is now the dominant recurring rail (53% share Jan 2025,
mandates 10x since Jan 2024). Razorpay supports it natively.

**Willingness to pay:** 70% of Indian AI users pay for zero subscriptions
(LocalCircles, 92K respondents). ChatGPT Go at ₹399 more than DOUBLED
OpenAI's Indian paying subscribers in ~a month — the price elasticity is
real. India ≈ 20% of global GenAI downloads, ~1% of in-app revenue.

**Spend reality:** typical paying Indian individual dev: ~₹400–5,000/mo on
AI tools/APIs, with a thin power-user slice at ₹8,000–17,000 (Claude Code
Max ≈ ₹16,800; a documented ₹1,600→₹80,000 bill-shock case is exactly our
buyer's nightmare). Small Indian startup: ~₹25,000–2,00,000/mo.

## 2. The analysis

**The founder's instinct is right about individuals — and the ruled ₹4,999
was priced for a different buyer.** India has TWO buyers, not one:

- **The individual dev** spends ₹2–5K/mo (power users ₹8–17K). At ₹4,999
  the audit tool costs 100%+ of most individuals' managed spend — the
  FinOps 1–3% ratio our own research established makes it unbuyable. For
  this buyer the correct comparison is not FinOps but the professional-tool
  entry band (₹800–1,500) — which is precisely the founder's ₹1,000–2,000
  band. At ₹1,999, a power user with a ₹17K/mo Claude Code habit pays ~12%
  of spend for control of it — steep vs the norm but rational against one
  bill-shock avoided.
- **The startup** spends ₹25K–2L/mo. For them ₹4,999 is 2.5–10% of spend —
  fine, even correct. Lowering everything to ₹1,999 leaves this segment's
  willingness on the table, but a 3-plan public ladder per country is
  simpler than inventing a 4th plan: the honest differentiator we already
  have is SOURCES (Pro=1, Scale=5). A startup with real spend has multiple
  keys/orgs → Scale is its natural home in India.

**Price points against evidence:** ₹1,999 = ChatGPT Plus India exactly, the
number lakhs of Indian professionals already pay monthly for an AI tool —
the strongest possible anchor for "professionals pay this for AI tooling."
₹999 maximizes reach but halves revenue against COGS that includes real
pulls+audits; ₹1,499 is the hedge. Scale at ₹14,999 is AFA-ceiling-perfect
and targets companies — the 7.5x gap to Pro is a feature (different buyer),
not a ladder break.

**The daily-ecosystem gap is real and is the bigger finding.** Today the
customer-visible loop is weekly (audit) to monthly (statement). At
₹1,999/mo an individual asks every renewal "what did it do for me this
week?" The data to answer DAILY already lands daily (scheduled pulls); what
is missing is only the daily SURFACE:
1. **Daily spend digest** (email): yesterday's spend per tool/source
   (Claude Code vs Cursor vs raw API — we already attribute by key), delta
   vs 7-day average, one line if a waste pattern is emerging. Rides the
   existing tick + mail + renderer machinery; COGS ≈ zero (data already
   pulled). This is the morning-check habit — the product becomes the
   place they LOOK every day, not the job they ran once.
2. **Dashboard "yesterday" tile** — same numbers, first thing on login.
3. **Budget line** — user sets a monthly ₹/$ cap, we alert as the
   month-to-date crosses 50/80/100% (rides the existing alert dispatch).
WhatsApp digest delivery is the true India-ecosystem endgame but a new
vendor surface — registered as a trigger, not built now.
Scope discipline: all three are NEW scope → they ship only under a ruling
(draft R-DAILY-LOOP below), and the honesty rail applies: the India tier
does not advertise the daily loop until it exists.

## 3. Founder counter (2026-07-21): "start from ₹500, pull the crowd,
## raise if demand increases" — assessment

**Viable, and specifically viable for THIS product.** The unit economics:
our engine is deterministic — zero LLM inference, zero GPU (the no-LLM
import guard is a COGS moat, not just a privacy stance). A subscriber
costs us metadata API pulls + rule evaluation + one email render: paise,
not rupees. ₹499 incl. GST nets ~₹413 after GST + Razorpay (~$4.7) —
comfortably above marginal cost. The proven India conversion point is
₹399–499 (ChatGPT Go doubled OpenAI's Indian paid base in a month at
₹399); ₹499 sits exactly on it.

**What ₹499 is and isn't:** it is a crowd/flywheel play, not a revenue
play — 100 subscribers = ₹50K MRR (~$570). Revenue stays in Scale
(₹14,999, companies, AFA-optimal) and the global tiers. The risks and
their answers:
- "Raise later" is only honest one way: raise the LIST price for future
  subscribers; early subscribers keep ₹499 for life (grandfathering).
  Label it "India launch price" plainly. Never a fake "was ₹999" anchor.
- A startup with one source gets a steal at ₹499 — acceptable while
  crowd is the goal; multi-source companies still land on Scale.
- Global-anchor gap ($99 vs ~$5.7): billing-country gating + the ChatGPT
  Go precedent make regional tiers normal; presented plainly per the
  honesty rail.
- THE condition: at ₹499 the crowd arrives on price and stays only on
  habit. Without the daily loop, cheap subscribers churn in month 2 —
  R-DAILY-LOOP is not an optional companion to this price, it is what
  makes the price work. Ship them together.

## 4. Draft spec for ratification — R-PRICING-FINAL-2 (amends §2 of R-PRICING-FINAL)

1. GLOBAL (founder final clarification 2026-07-22: India ₹500 IS the
   ~$5 tier; global prices are DIFFERENT — "properly set for global
   business spending"): the PPP-fair structure the founder selected.
   Pro LAUNCH $19/mo → LIST $29/mo (first 200 global paid subscribers
   grandfathered for life; flip enforced in code at #200). Scale
   LAUNCH $59/mo → LIST $99/mo (same cohort window). Rationale: $29 to
   a US buyer is the same FELT cost as ₹999 to an Indian buyer —
   fairness adjusted for purchasing power, not FX — while still
   60-75% below every competitor (Helicone $79, Langfuse Pro $199,
   Portkey $49 entry). One-shot audits stay $500 / ₹20,000
   (founder-time service). Anchor line: "less than a tenth of what
   observability platforms charge — and it pays for itself in found
   waste." Earlier candidate structures ($99/$299 ruled too high;
   $49/$149; literal $4.99 parity — a misreading, retired same day)
   are superseded by this section.
2. INDIA (Razorpay/INR, billing-country gated, same features/gates):
   - Pro: LIST ₹999/mo incl. GST; LAUNCH ₹499/mo for the first 200
     India subscribers, grandfathered for life (founder margin
     amendment 2026-07-21). The page states the cohort plainly
     ("₹499/mo — launch price for the first 200 India subscribers;
     ₹999 after"); the flip is enforced in code (config carries both
     prices + cohort size, auto-flips at paid subscriber #200).
   - Scale ₹14,999/mo KEPT (company tier, 5 sources, under the ₹15,000
     RBI AFA ceiling so renewals stay frictionless; UPI Autopay primary).
   - One-shot ₹20,000 unchanged.
3. R-DAILY-LOOP (coupled, ~2 days build): daily spend digest email
   (per-tool attribution, delta vs 7-day average) + dashboard
   yesterday-tile + user budget line with 50/80/100% alerts, for ALL
   paid plans globally (retention is not a geo feature). The India tier
   launches WITH it; it is not advertised before it exists. WhatsApp
   delivery = registered trigger.
4. Guardrails and honesty rail exactly as R-PRICING-FINAL §3–4: config-only
   prices, currency by billing country with toggle, INR/USD no-mixing test,
   PPP presented plainly as regional pricing, no fake discounts.

## 5. Worth test (founder challenge 2026-07-22: "is our solution worth
## those dollars? think again")

What a subscriber actually gets: daily read-only pulls, weekly
deterministic audits (retry storms, model misrouting, cacheable repeats,
token bloat), evidence-backed findings, alerts, and VERIFIED savings
statements — verification against subsequent usage is the rare part.
Honest bounds: retrospective (not a real-time gateway — X-01), advises
but doesn't auto-fix, v1 detector coverage, daily loop not yet built.

Worth is a function of the CUSTOMER'S spend, so the honest answer is a
segmentation, not a yes/no:
- Spend <$100/mo (hobbyist): NOT worth paying — findable waste is less
  than the fee. They belong on Free by design (future customers).
- $100–650/mo (indie dev / power user): borderline on savings alone;
  worth rides on the daily loop (attribution, budget guard, bill-shock
  prevention — the ₹80K-bill story). This is exactly who ₹499/$19 aims
  at.
- $650–5K/mo (small team): clearly worth — 10-20% findable waste means
  findings return 5–20x the $29 fee. The core Pro buyer.
- $5K–100K/mo (company): Scale $99 is dramatically UNDER value —
  deliberate penetration; upside lives in one-shots + the success-fee
  experiment + day-45 repricing data.

The structural answer to "worth it?": the FREE AUDIT is the proof
mechanism. Every prospect sees "we found $X/mo of waste" from their own
data before paying anything — if X exceeds the fee, worth is proven by
our own report, per customer, not asserted by marketing. Therefore the
pricing page carries an honest QUALIFYING line instead of a universal
pitch: "Spending more than ~$500/mo on AI? Pro pays for itself. Less?
Start free — we'll be here when your bill grows." Self-qualification is
also a trust signal no competitor uses.

Ruling requested: "PRICING-FINAL-2 CONFIRMED" plus "R-DAILY-LOOP GO" /
amendments by number. Config untouched until ruled.
