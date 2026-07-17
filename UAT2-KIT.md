# UAT-2 KIT — external design-partner audit (docs/05 §5)

UAT-2 is founder-executed: one friendly external partner gets a free audit,
and the thing under test is whether the PUBLIC export instructions
(docs-site quickstart) are comprehensible **without a call**. This kit makes
the send a copy-paste; the record of the result closes the vv gate's open
finding.

## 1. The email to send (copy-paste, edit the greeting)

> Subject: Free LLM cost audit — 15 minutes of your time, no integration
>
> I built a tool that turns LLM API logs into a dollar-ranked waste audit —
> no SDK, no proxy, nothing in your request path. I'd like to give you a
> free audit as an early design partner, and honestly, the thing I'm
> testing is whether my export instructions make sense without me on a
> call.
>
> Steps:
> 1. Export your logs per the instructions here: <quickstart URL, or the
>    attached quickstart.md if the site isn't public yet>. OpenAI/Anthropic
>    JSONL, a generic CSV, or — if your spend is Claude Code — the bundled
>    exporter script (token counts only; your prompt text never leaves your
>    machine).
> 2. Send me the export file (or upload it once I send your sign-in link).
> 3. You get a PDF report within 48h: every finding evidence-backed, ranked
>    by monthly dollar impact.
>
> Data policy, verbatim from our terms: uploaded logs are
> "analyzed then deleted; nothing retained beyond 7 days; never used for training."
> No prompt text is ever stored — the engine keeps token counts only, and
> that's enforced by automated tests, not just policy.
>
> One ask in return: note anywhere you got stuck or had to guess. That
> feedback is the product.

## 2. What to record (the UAT-2 evidence, one paragraph in STATUS.md)

- Date, partner (anonymized is fine: "partner A, ~$Xk/mo spend, provider Y")
- Export format they chose; whether they completed the export WITHOUT a
  call/clarifying question (the exit criterion) — and if not, verbatim where
  they got stuck
- Audit ran clean? (row validity %, unpriced models, runtime)
- Their reaction to the report (the docs/05 readability criterion applies:
  a non-founder CTO reads it in <10 minutes)
- Any finding they judged wrong or embarrassing → same defect ritual as
  UAT-1/UAT-D5 (fix ruling, regression pin, NOTES entry)

## 3. Exit criteria (docs/05 §5, founder-certified)

- [ ] Export instructions comprehensible without a call
- [ ] Zero false-positive findings judged embarrassing (their read)

If the partner's traffic surfaces a defect: that is the kit working —
UAT-1 caught five before any customer saw them; UAT-2 exists to catch the
sixth on friendly ground.
