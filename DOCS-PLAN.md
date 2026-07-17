# DOCS-PLAN.md — public documentation site (milestone D-DOCS)

Status: APPROVED by founder 2026-07-17 (all three §6 choices confirmed).
Founder addition: every waste-class subpage ends with a "Known limitations"
line where applicable (e.g. the OpenAI cache-write TRACKED GAP on the D2 page) —
honesty in public, consistent with the R-GOLDEN-C3 floors language.
Derived from the internal spec kit (docs/00-10) — link/derive, never fork.
Build state at planning time: D4 complete; G4 not passed → per TIMING rule this
milestone ships skeleton + IA + measurement-free pages, with MEASUREMENT-PENDING
blocks for everything else (list in §4). Invented numbers = FAIL.

## 1. Stack decisions

- MkDocs + Material, source `docs-site/`, config `mkdocs.yml` at repo root.
- DEV dependencies (authorized by the D-DOCS task itself; recorded as R-DEPS
  extension): `mkdocs-material` only. No other plugins — every need below is
  covered by Material built-ins: Mermaid via pymdownx.superfences (bundled, no
  CDN), tabbed code blocks via pymdownx.tabbed, admonitions, and file
  transclusion via pymdownx.snippets (used to auto-include docs/04 so the
  traceability matrix can never drift).
- No trackers, no external CDNs: `font: false` in mkdocs.yml; typography via a
  local system stack tuned to IBM Plex/Inter class (`extra.css`); Material's
  JS/CSS is self-contained; Mermaid renderer ships inside Material.
- Palette (Claude-docs-like): light scheme on warm neutral (#faf9f5 body,
  #1a1a17 text), single clay/terracotta accent (#c96442) for links/active nav;
  dark scheme mirrored (#1f1e1b bg). Generous spacing + slightly narrowed
  content column in `docs-site/stylesheets/extra.css`.
- API reference: no mkdocstrings; a build step `scripts/export_openapi.py`
  dumps `openapi.json` from the app factory and renders endpoint tables to
  `docs-site/api/endpoints.md` (regenerated in CI; CI fails if drift).
- CI: new `docs` job in .github/workflows/ci.yml — `uv run python
  scripts/export_openapi.py --check` then `uv run mkdocs build --strict`
  (zero warnings) and upload `site/` as a build artifact.
- Git: branch `d-docs` off main (D4 branch stays untouched); traceability DOC
  column lands in the same commit as the pages (CLAUDE.md rule 5).

## 2. Page tree (sidebar order) — one-line content summary per page

```
docs-site/
├─ index.md                       Home: three-sentence definition; CTO-voiced problem
│                                 statement using ONLY docs/09b §3 attributed stats
│                                 (79%, 31%, 98% w/ attribution); what you get (report
│                                 screenshot PLACEHOLDER, MP-2); "what we never do" with
│                                 FR-23 policy string verbatim + FR-21/22 in plain terms.
├─ quickstart.md                  Export → upload → read report in 3 steps; per-provider
│                                 export tabs (OpenAI JSONL / Anthropic JSONL / generic
│                                 CSV contract) + Claude Code exporter copy-paste (works
│                                 today, tested); upload/report steps MP-1 pending D6-D8.
├─ concepts/
│  ├─ how-it-works.md             Pipeline ingest→normalize→price→detect→report; one
│  │                              Mermaid diagram derived from docs/02 §3; determinism
│  │                              framing (NFR-01: no LLM in the engine).
│  ├─ waste-classes/
│  │  ├─ index.md                 The six classes at a glance (table: what/severity
│  │  │                           logic/confidence labels); links to per-class pages.
│  │  ├─ oversized-model.md       D1: problem/detection/estimate/fix. Spec-derived now
│  │  │                           (docs/03 §3); golden example MP-10 (D5).
│  │  ├─ missing-cache.md         D2: full R-Q4/R-Q5 estimation math in prose + formula
│  │  │                           (est_writes TTL windows, per-family TTL C4, haircuts);
│  │  │                           worked golden example (REAL: $0.246784/mo fixture).
│  │  ├─ prompt-bloat.md          D3: spec-derived; golden example MP-10 (D5).
│  │  ├─ retry-storms.md          D4: anchor-window clustering, (n−1)×mean-cost; worked
│  │  │                           golden example (REAL: $0.0510/mo fixture).
│  │  ├─ unbounded-max-tokens.md  D5: informational finding semantics; MP-10 (D5).
│  │  └─ chatty-loops.md          D6: agent re-read signature; MP-10 (D5).
│  ├─ pricing-data.md             TRUST FEATURE framing (R-PRICING-OPS): rates versioned,
│  │                              effective-dated, human-verified; each call priced at the
│  │                              rate in effect at its timestamp; live/scraped pricing
│  │                              refused for money math by design. Four-rate
│  │                              model, 5.6-family TTL difference (C1/C4), dated-snapshot
│  │                              prefix matching, "unpriced model" report behavior.
│  └─ data-handling.md            Lifecycle Mermaid (upload→analysis→report→7-day purge);
│                                 what is NEVER persisted (FR-22 mechanics: hashes not
│                                 text); append-only audit log; FR-23 string verbatim.
├─ api/
│  ├─ overview.md                 Auth (magic link → session; admin token), rate limits
│  │                              (NFR-03), upload constraints (200MB, formats), signed-
│  │                              URL semantics (30-day expiry), error taxonomy from
│  │                              docs/03 §8 with user-facing messages, and the NFR-14
│  │                              uniform error envelope (R-API). Spec-derived.
│  └─ endpoints.md                GENERATED from openapi.json: every docs/03 §5 endpoint,
│                                 curl + Python httpx tabs. Skeleton now (only /healthz
│                                 exists); MP-3 grows at D6 (audits), D7 (/r/), D9
│                                 (webhooks). Examples marked verified-on-run only.
├─ report/
│  ├─ reading-a-report.md         Field-by-field: exec summary, charts, waterfall,
│  │                              Finding anatomy (severity/confidence/monthly impact/
│  │                              evidence rows ≤20). Structure spec-derived (docs/03 §2,
│  │                              FR-13/14); rendered-artifact specifics MP-4 (D6/D7).
│  └─ worked-example.md           waste_pack fixture walk-through with REAL golden
│                                 numbers (D2/D4 today; full set MP-8 at D5) + the
│                                 derivations from pricing_golden_NOTES.md.
├─ engineering/
│  ├─ index.md                    Why this section exists (transparency = the product).
│  ├─ requirements.md             FR/NFR intent grouped human-readable (ingestion,
│  │                              analysis, reporting, accounts, lifecycle, ops), linked
│  │                              to concepts pages; no raw ID dump.
│  ├─ architecture.md             HLD summary (monolith + boundaries, ADR-1..7 in prose);
│  │                              spec-derived component diagram now; architect-generated
│  │                              UML embedded at MP-5 (post-G4, D6 content).
│  ├─ stack.md                    Tech choices + why, from PLAN.md §0 decisions: Python
│  │                              3.14 (verification evidence), pandas/pyarrow, no-LLM
│  │                              engine as feature ("deterministic by construction —
│  │                              the analysis engine cannot hallucinate", NFR-01).
│  ├─ traceability.md             The req→design→code→test discipline explained; matrix
│  │                              auto-included from docs/04 via snippets (never drifts).
│  ├─ testing.md                  docs/05 strategy in prose: L1-L5; black-box golden-
│  │                              fixture approach (known-waste-in/exact-findings-out +
│  │                              clean-fixture FP guard), hypothesis reconciliation
│  │                              property (NFR-07), import guard (T-NFR-01, notes MP at
│  │                              D5); universal Definition of Done from PLAN.md §1
│  │                              intro published verbatim.
│  ├─ integration.md              Compose topology (caddy→app→postgres+ofelia) Mermaid;
│  │                              dev/staging/prod environments; CI stage diagram
│  │                              (lint→type→test→coverage→build→docs).
│  ├─ security.md                 Threat-model summary from docs/02 §6 + runbook §5:
│  │                              magic-link semantics, cookie flags, admin isolation,
│  │                              upload hardening, TLS/headers, secrets, rate limits,
│  │                              append-only audit log, additive-only migrations;
│  │                              X-01..X-05 published as self-enforced product
│  │                              boundaries.
│  └─ performance.md              NFR-04 target stated; ALL numbers MP-6/7: measured 1M-
│                                 row wall-clock + machine spec, per-stage timings from
│                                 scripts/bench.py (new, + "bench" pytest marker), memory
│                                 peak, determinism repeat-run proof; detector efficacy
│                                 table (golden precision + clean-fixture zero-FP — D2/D4
│                                 rows REAL today, rest MP-8); honest limitations list.
├─ limits.md                      v1 limits from docs/01 §G + methodology caveats
│                                 (aggregate-only providers, unpriced models, C3
│                                 surcharge floors, OpenAI 5.6 write-count gap). No
│                                 Phase-2 promises, no dates.
└─ legal/
   ├─ terms.md                    STUB → MP-9: single-sourced with D8 ToS page.
   ├─ privacy.md                  STUB → MP-9: single-sourced with D8 privacy page
   │                              (must carry FR-23 string verbatim).
   └─ dpa.md                      STUB → MP-9: DPA-lite one-pager (PRD §9).
```

Every factual page carries `<!-- src: ... -->` comments per claim (spec section,
test ID, or measured-run reference). Voice: second person, short sentences, no
hype, no emoji.

## 3. Claude-docs-style presentation checklist

Left sidebar nav (sections above), right-side on-page TOC (`toc.integrate` OFF,
`navigation.tabs` OFF — single sidebar like docs.claude.com), tabbed code blocks
(curl/Python), admonitions for privacy/limits callouts, dark/light toggle,
`navigation.indexes` for section landing pages, local search.

## 4. MEASUREMENT-PENDING register (the complete list)

| ID | Item | Unlocks at | Notes |
|----|------|-----------|-------|
| MP-1 | Quickstart upload+report steps & "10 minutes, tested end-to-end" claim | D6 (upload API) / D7 (report) / D8 (auth) | Export step is testable TODAY (exporter + fixtures); timing claim only after a timed e2e run |
| MP-2 | Sample report screenshot on Home | D7 | placeholder box until then |
| MP-3 | API endpoint tables + verified request/response examples | D6 / D7 / D9 | page regenerates from openapi.json each CI run; grows as endpoints land |
| MP-4 | Report Reference field-by-field against the real artifact | D6 (JSON) / D7 (PDF/web) | structure documented from spec now |
| MP-5 | Architect-generated UML (components + audit sequence) embedded | post-G4 (end D7) | spec-derived diagram used meanwhile, labeled as such |
| MP-6 | Performance numbers: 1M-row wall-clock + machine spec, per-stage timings, memory peak (scripts/bench.py + `bench` marker) | post-D6 runner; full 1M at D12 perf fixture | NFR-04 target may be STATED (spec); results only after measured runs. FOUNDER PRECONDITION (R-SEQ-UAT1): at least one successful NIGHTLY perf run must exist before this page fills |
| MP-7 | Determinism proof (same input → byte-identical findings JSON, repeat-run test) | D6 (render_json) | detector-level determinism exists implicitly; the published claim waits for the JSON-artifact test |
| MP-8 | Detector efficacy table rows for D1/D3/D5/D6 + full-fixture precision statement | D5 (waste_pack v2 goldens) | D2/D4 rows publishable NOW from existing goldens |
| MP-9 | Legal page content (ToS/Privacy/DPA-lite) | D8 | mechanism decision at D8: masters live in docs-site/legal/, web pages render the same source (no forking) |
| MP-10 | Golden worked examples inside D1/D3/D5/D6 class pages | D5 | detection logic itself is spec-derived and documented now |

Numbers publishable TODAY (already measured/derived in-repo): D2 golden
$0.246784/mo and D4 golden $0.0510/mo (pricing_golden_NOTES.md derivations),
the 15 pricing golden rows, coverage figures if quoted as of a stated commit.

## 5. Delivery order after approval

1. Scaffold: mkdocs.yml, extra.css, nav, CI `docs` job, export_openapi.py.
2. All measurement-free pages (Home, Concepts, api/overview, Engineering a-g
   minus numbers, Limits, Report structure, worked-example D2/D4 portion).
3. MEASUREMENT-PENDING admonition blocks (visually distinct, greppable token
   `MEASUREMENT-PENDING`) at every MP site.
4. docs/04-TRACEABILITY.md: add DOC column (requirement group → covering page).
5. `mkdocs build --strict` zero-warning check in CI + artifact upload.
6. Gates: ux-reviewer (extended to docs-site/: clarity, nav, jargon, FR-23
   string) and spec-guard (10-random-claim source spot check). Report verdicts.

## 6. Open items for founder at approval

1. Waste classes as six subpages (chosen: deep-linkable from future report
   findings) vs one long page — confirm or flip.
2. Domain/base-url for the site (affects mkdocs `site_url`; artifact-only for
   now, no publishing target assumed).
3. Confirm dev-dep set (mkdocs-material only) satisfies the "plugins" clause —
   plan deliberately avoids third-party plugins.
