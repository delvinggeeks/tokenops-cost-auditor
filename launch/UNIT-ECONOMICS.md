# Unit economics & profit model (founder question, 2026-07-21)

Scenario math, not predictions: revenue depends entirely on subscriber
counts, which are unknown pre-launch. What IS structural: the margin per
subscriber and the fixed-cost floor. FX at ₹88/USD. Prices per
R-PRICING-FINAL(-2 draft): global $99/$299/$500 one-shot; India ₹499
launch / ₹14,999 / ₹20,000 one-shot.

## 1. What survives from each payment (contribution per subscriber/month)

| Line | List | GST out | Payment fee | Net to us |
|---|---|---|---|---|
| India Pro | ₹499 incl. GST | −₹76 (18% within) | −₹10 (Razorpay ~2%, ITC netted) | **~₹413 (~$4.7)** |
| India Scale | ₹14,999 incl. GST | −₹2,288 | −₹300 | **~₹12,410 (~$141)** |
| India one-shot | ₹20,000 | −₹3,051 | −₹400 | **~₹16,550 (~$188)** |
| Global Pro | $99 | zero-rated (export, LUT) | −~5% (Stripe intl+FX) | **~$94** |
| Global Scale | $299 | zero-rated | −~5% | **~$284** |
| Global one-shot | $500 | zero-rated | −~5% | **~$475** |

Key structural facts:
- **Marginal COGS ≈ 0.** The engine is deterministic — no LLM inference, no
  GPU (T-NFR-01's no-LLM import guard is a COGS moat). A subscriber costs
  metadata API pulls + rule evaluation + email renders: paise.
- **Exports are GST-zero-rated** (file LUT annually) — global revenue takes
  no 18% haircut, only Stripe's ~5%.
- GST on Razorpay/Stripe fees is input-creditable — netted above.

## 2. Fixed cost floor (monthly — FOUNDER-CONFIRMED 2026-07-21)

VPS ₹2,000/mo + miscellaneous ≈ **₹5K/mo total (~$57)**. Founder time not
costed (owner-operated). Zero ad spend assumed (launch per
R-LAUNCH-POSITIONING is organic). Paid acquisition, if ever, becomes the
dominant cost and invalidates the scenarios below. At 100 subscribers
fixed costs are already ~3% of revenue — the margin lever is price ×
retention, never cost.

## 2a. Founder margin question (2026-07-21) → two-cohort structure

Founder: raise prices, keep USD for international, increase margin.
Resolution proposed: **India Pro LIST ₹999/mo; LAUNCH ₹499/mo for the
first 200 India subscribers, grandfathered for life.** Crowd logic kept
(proven ₹399–499 conversion point for the first cohort), margin doubled
from subscriber #201 (~₹827 net vs ~₹413). Honesty rail: the page states
plainly "₹499/mo — launch price for the first 200 India subscribers;
₹999 after" — a checkable claim, and the flip is enforced IN CODE
(config carries both prices + cohort size; auto-flips at paid subscriber
#200), not by memory.

Founder FINAL clarification 2026-07-22: India ₹499/₹999 IS the ~$5/$11
tier for the Indian market; GLOBAL is a DIFFERENT, higher set matched to
global business spending — the PPP-fair structure the founder selected:
Pro LAUNCH $19 → LIST $29, Scale LAUNCH $59 → LIST $99 (first-200
global cohort, grandfathered, code-enforced flip). One-shots stay
$500/₹20,000. Net per global subscriber after Stripe intl fees: Pro
launch ~$17.9 / list ~$27.4; Scale launch ~$55.7 / list ~$93.6.
Scenario shape: seed (100 India + 20 global Pro launch) ≈ ₹75K/mo
pre-tax ≈ ₹6.7L/yr after tax; base case (300 India mixed, 5 India
Scale, 60 global Pro mixed, 8 global Scale, 2 one-shots/mo) ≈ ₹3.7L/mo
pre-tax ≈ ₹33L/yr after tax; scale-out (1,000 India, 25 India Scale,
300 global Pro, 30 global Scale, 6 one-shots) ≈ ₹17L/mo pre-tax ≈
₹1.5Cr/yr after tax. Margins stay ~85-95% (COGS≈0); profit scales
linearly with retained subscribers; retention (R-DAILY-LOOP) remains
the load-bearing mechanism at these price points.

## 3. Scenarios (monthly, steady state; two-cohort India Pro:
## first 200 at ₹499 grandfathered, ₹999 list after)

| | Seed crowd | Base (mo. 6–12) | Scale-out (yr 2 target) |
|---|---|---|---|
| India Pro (₹499 cohort / ₹999) | 100 / 0 | 200 / 100 | 200 / 800 |
| India Scale | 0 | 5 | 25 |
| Global Pro | 5 | 20 | 100 |
| Global Scale | 0 | 3 | 15 |
| One-shots /mo | 0.3 | 2 | 6 |
| **Net revenue** | ~$1.1K | ~$6.0K | ~$28.5K |
| Fixed costs (₹5K; scaled*) | −$0.06K | −$0.1K | −$1.5K* |
| **Pre-tax profit** | **~$1.05K (₹92K)** | **~$5.9K (₹5.2L)** | **~$27K (₹23.8L)** |
| After 25.17% corp tax | ~$0.78K (₹69K) | ~$4.4K (₹3.9L) | ~$20.2K (₹17.8L) |
| **Annualized after-tax** | **~₹9L/yr** | **~₹47L/yr** | **~₹2.2Cr/yr** |

*Scale-out adds bigger VPS + tooling + part-time support assumption.

## 4. The tax line depends on WitAura's legal form (CONFIRM WITH A CA)

- **Pvt Ltd (115BAA): 25.17%** effective on profits — used above. Personal
  extraction (salary/dividend) adds the founder's slab tax on top.
- **LLP: 31.2%.**
- **Sole proprietorship:** slab rates; AND if turnover ≤ ₹3Cr with 95%+
  digital receipts, **presumptive 44AD** may tax only 6% deemed profit on
  turnover — at our ~90% real margin this can push effective tax near zero
  in early years. Material planning point; needs a CA's confirmation that
  SaaS subscription income qualifies as eligible business income.
- US customers create no US tax (no US permanent establishment); Stripe
  export settlement needs FIRC records.

## 5. The honest punchline

After fees and GST, ~83% of every Indian rupee and ~95% of every export
dollar reaches profit before income tax, and the fixed floor is under
₹10K/mo. The platform's profit is therefore almost exactly a function of
ONE variable: paying subscribers retained. Cost will never be the problem;
acquisition and retention are the whole game — which is why the ₹499
crowd-pull only works coupled to the daily loop (R-DAILY-LOOP), and why
the walkthrough → launch chain matters more than any line in this file.
