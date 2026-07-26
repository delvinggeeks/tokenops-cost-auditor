# QUEUE — the single work spine

The one ordered, traceable list of what to build next. Agents read THIS top-to-bottom.
It does **not** copy the spec — it links it, and stays small on purpose (a big plan is
how agents hallucinate). Detail lives in the sources; sequence lives here.

## Sources (authoritative — link, never duplicate)

| Layer | Doc | Owns |
|-------|-----|------|
| WHAT | `docs/01-REQUIREMENTS.md` | FR/NFR + X-scope (the single requirement source) |
| DONE | `docs/04-TRACEABILITY.md` | req → module → test (proof of shipped) |
| HOW | `docs/09-SDLC.md` | slice lifecycle, DoD, gate set |

## Law (this is how we stop diverging)

1. Work **top-down from NOW**. One task = one vertical slice = one `loop:ready` issue, and it **cites its FR/NFR**.
2. **Nothing is built that isn't a NOW task here.** A new idea → `docs/01` (real scope) or `BACKLOG.md` (one line), never straight to code.
3. **Done = its `docs/04` row updated in the same PR** + gate round green. No other "done".
4. This file is the control surface, set up by hand; the **tasks on it go through the loop** (card → fresh session → reviewers → merge).

## NOW — buildable, in order

_Empty. All 48 FR/NFR are shipped + traced (`docs/04`); the product frontier is
exhausted (2026-07-26). Nothing is silently missing — verified by req↔trace diff._

> When scope opens, each task lands here as one line:
> `T-<id> · FR-xx · <vertical-slice one-liner> · trace: <module>→<test>`

## BLOCKED — needs a founder action first (ROADMAP §4)

- **LE-2 continuous deploy** ← set `DEPLOY_HOST/DOMAIN/SSH_KEY`. (The only rung left; LE-1/3/4/5/6 shipped.)
- Branch-protection · Stripe/OAuth creds · domain cutover · UAT-2 · pending rulings — full list: `ROADMAP §4`.

## PARKED — trigger-gated, do NOT pull forward (ROADMAP §5)

Each fires on a named customer/demand event. Pulling one forward without its trigger
**is** the divergence we're stopping.

- S-2 OTLP ← first streaming customer · S-3 MCP ← API-key signal · O-3 SSO ← first team customer
- M-FLY-2 calibration ← n≥25 peer data · D7 export detector ← day-45 · (full list: `ROADMAP §5`)

## Superseded for SEQUENCING → this file

`internal/ROADMAP`, `internal/PLAN(+PLAN-*)`, `KANBAN`, `BACKLOG`, `docs/07-ROADMAP`
still hold reference/design detail, but **what to build next comes from here** — not from them.
