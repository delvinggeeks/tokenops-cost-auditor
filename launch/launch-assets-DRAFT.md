# D14 launch assets — DRAFT, FOUNDER APPROVAL REQUIRED

Rules applied (R-SELF-AUDIT d): ONLY ledger-verified / founder-approved
figures appear below — the verified ledger row 1 and the corrected UAT-1 set
approved post machine-check. Equiv-spend framing attached wherever those
figures appear. Stats policy: only attributed 79%/31%/98%. Nothing here
publishes until the founder approves this file AND the D14 spec-guard sweep
passes.

Figure inventory (the ONLY numbers permitted in any asset):
- Ledger row 1 (founder-verified 2026-07-17): 1,340 calls · $432.27 observed ·
  est. $1,966.27/mo waste · 30.3%
- Ledger row 2 (founder-verified 2026-07-19): 1,478 calls · $512.92 observed ·
  est. $1,525.61/mo waste · 29.7%
- Corrected UAT-1 set (founder-approved, machine-checked): 67,095 unique
  calls from 159,571 events (58% duplicates) · $8,757.75/mo API-equivalent ·
  $2,846.62/mo est. waste · 32.5%
- Price list, as shipped (renders from the one price config, never inline):
  Free $0 no card · Pro $99/mo · ₹8,999/mo · Team $299/mo · ₹26,999/mo ·
  one-off audit $500 · ₹45,000
- Defect narrative: the 228% claim our golden discipline caught; the ledger
  row our own verification gate refused (UAT-D5)
- Market stats (attributed only): 79% overran AI budgets (DoiT/Sapio, 2026);
  even mature FinOps teams overspent 31% (same survey); 98% of FinOps teams
  now manage AI spend (State of FinOps, 2026)
- Mandatory rails, verbatim, wherever our own numbers appear:
  "Figures are API-equivalent token value; actual billing depends on your
  plan." · "n=1, uncontrolled — your logs are the real test."

---

## Asset 1 — launch thread (X/LinkedIn, ~8 posts)

**1/** Just got an AI bill you can't explain? That moment is exactly what
we build for: upload your LLM logs, get back a dollar-ranked list of what
was waste.

We pointed it at the AI agents that built it: 32.5% waste. Then our own
verification process rejected its first report. Twice. That's the story
worth telling.

**2/** The product: upload your LLM API logs → deterministic, dollar-ranked
waste audit in 48h. No SDK, no proxy, nothing in your request path. Six
waste classes: missing prompt caching, retry storms, oversized models,
prompt bloat, unbounded output caps, chatty agent loops.

**2b/** New in this build: connect your provider read-only and it keeps
auditing — scheduled re-audits, alerts when spend moves, a monthly savings
statement showing what you actually banked. Read-only means read-only: we
pull usage counts from the official admin API. There is no prompt text in
that API, so there is none in our database either.

**3/** First rejection: the audit of our own build sessions claimed 228% of
spend as "savings." Impossible number. Root cause: we priced prompt-token
savings at full input rate, but ~95% of agent-session tokens are billed as
cache reads at a tenth of that. Fixed, regression-pinned, disclosed in the
methodology.

**4/** Second rejection: our first self-audit ledger row failed founder
verification — the log exporter was counting one row per transcript EVENT,
not per completed API call. 58% of rows were duplicates. The row was
discarded; the exporter now prints its dedup arithmetic on every run.

**5/** Why tell you this? Because an audit product's only real asset is
arithmetic you can check. Every number traces to a versioned, human-verified
rate card and a hand-derived golden test. When the numbers were wrong, the
discipline caught them BEFORE launch — and the discipline is the product.

**6/** The verified numbers, then: our build's own audited traffic —
67,095 API calls, $8,757.75/mo API-equivalent spend, $2,846.62/mo estimated
waste (32.5%). "Figures are API-equivalent token value; actual billing
depends on your plan." And: n=1, uncontrolled — your logs are the real test.

**7/** The industry context (attributed): 79% of enterprises overran their
AI budgets last year (DoiT/Sapio, 2026); even mature FinOps teams overspent
31%. 98% of FinOps teams now manage AI spend (State of FinOps, 2026) — with
tools that need integration before they show you anything. Ours needs a log
file.

**8/** Start free — one full audit of a log file you upload, no card. Keep it
watching for $99/mo (₹8,999) — connect your provider read-only and it audits
on a schedule, alerts on spend moves, and posts you a monthly savings
statement. One-off audit for enterprises: $500 (₹45,000). Your data:
"analyzed then deleted; nothing retained beyond 7 days; never used for training." Docs — including our full methodology, our defect log, and the
audit of ourselves — at <docs URL>. DM or <site URL> to start.

---

## Asset 2 — HN/forum post (show-don't-sell register)

Title: We audit LLM token waste — our own tool's first report was wrong, and
our verification gate refused it

Body: We're building a zero-integration LLM cost auditor (upload logs → 
deterministic dollar-ranked waste report; engine has zero LLM calls,
enforced by an import-guard test — determinism is the feature). Before
launch we pointed it at the Claude Code agents that built it. First report:
228% of spend as "savings" — we priced cache-read tokens at full input rate.
Second attempt: our founder-verification step rejected the first published
ledger row because the exporter double-counted transcript events (58%
duplicate rows). Both defects are now regression tests, and the defect log
is published on the docs site next to the methodology, because for an audit
product the discipline IS the product. Verified numbers from auditing
ourselves: 67,095 calls, $8,757.75/mo API-equivalent, 32.5% estimated waste
("API-equivalent token value; actual billing depends on your plan" — n=1,
uncontrolled; your logs are the real test). Happy to answer anything about
the detection math — every estimator's formula and haircuts are public.

---

## Distribution — trigger-moment targeting (R-PAINMOMENT, founder 2026-07-20)

Outreach targets TRIGGER MOMENTS, not cold personas:

a. **Search-and-reply, not broadcast**: find X/Reddit/HN posts complaining
   about OpenAI/Anthropic/Claude Code bills; reply with the free audit
   offer. Replies follow the same rules as the assets: figure inventory
   only, rails attached, no hype. CONNECT IS NOW CLAIMABLE (V-D10,
   2026-07-23) — it ships in this build, so replies may describe the
   read-only provider connection and scheduled re-audits as things that
   exist today. The old "no Connect claims" rule is retired, not relaxed:
   it existed because Connect was unbuilt, and that is no longer true.
b. **Model-release weeks**: cost profiles shift when providers ship new
   models/prices — audit demand spikes; time outreach pushes to those
   windows (pricing-watch WP-P1.5 will surface them once live).
c. **Hook discipline**: the thread hook leads with the bill-shock scenario,
   not the category (applied to Asset 1 post 1/).

## Registered lines (not yet approved for use)

- "We run the architecture we audit you toward." (R-ARCH-PATTERNS b)
- "Install the auditor inside the agent that's burning the tokens."
  (R-SKILL 3 — usable once WP-SKILL actually ships, never before)
- "Your traffic's shape tells us what it's doing — you tell us why — we
  never read what it says." (R-INTENT-LADDER b)

## Approval checklist (founder)

- [ ] Figures match the inventory above, nothing else numeric
- [ ] Prices match the shipped price config ($500 · ₹45,000 one-off; the
      assets previously published ₹20,000, a rate we do not charge — the
      same stale figure was live in the Terms of Service until V-D10)
- [ ] FOUNDER CALL OUTSTANDING: post 8/ now leads with Free→Pro subscription
      and demotes the $500 one-off to an enterprise line. That is a
      positioning change, not a figure correction — confirm or reorder.
- [ ] Rails present wherever our numbers appear
- [ ] FR-23 string verbatim in asset 1/8
- [ ] URLs filled (site, docs) post-deploy
- [ ] Tone: no hype; hook = bill-shock moment (R-PAINMOMENT), then the
      defect story leads the body
