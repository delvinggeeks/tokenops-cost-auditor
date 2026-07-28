# TokenOps documentation — start here

Two documentation worlds, one rule: **public teaches the product; internal teaches the
platform.** Nothing is duplicated between them — each fact has one home.

| World | Lives in | Audience | Rendered |
|---|---|---|---|
| **Public** | `docs-site/` | customers + external developers | the docs site (mkdocs; `endpoints.md` is generated — never hand-edit, run `scripts/export_openapi.py`) |
| **Internal** | `docs/` + `docs/internal/` | platform developers + the loop's agents | read in-repo |

## Internal reading order (new platform dev, ~half a day)

1. **`00-PRD.md`** — §1 the validated problem statement, personas, value prop, scope.
2. **`01-REQUIREMENTS.md`** — every FR/NFR + the X-scope freeze (what we will NOT build and why).
3. **`02-HLD.md`** — architecture overview, component→requirement map, the audit happy-path
   data flow, ADR summary (tech-stack decisions live here; the public mirror is
   `docs-site/engineering/stack.md`).
4. **`internal/CODE-TOUR.md`** — the same architecture, but walked through real files in
   plain language, 16 stops: the audit pipeline (Part 1) then the platform-era systems
   around it — orgs, the developer platform, flywheel, statements (Part 2).
5. **`12-FLYWHEEL.md`** — the intelligence lifecycle: five ingestion tiers, the
   deterministic engine, the L0–L4 learning ladder with its honesty thresholds, intent law.
6. **`internal/LIFECYCLE-MAP.md`** — one table: every lifecycle capability, its status,
   authority, and trigger. The completeness view.
7. **`03-LLD.md`**, **`05-TEST-PLAN.md`**, **`06-OPS-RUNBOOK.md`** — reference as needed.

## The overview in one diagram

```mermaid
flowchart LR
    subgraph COLLECT["COLLECT (5 tiers, docs/12)"]
        T1["T1 file/CLI ✅"] --> N
        T2["T2 account APIs ✅"] --> N
        T3["T3 collector 📋"] -.-> N
        T4["T4 OTLP 📋"] -.-> N
        N["ingest/normalize<br/>(counts only, FR-22)"]
    end
    subgraph ENGINE["ENGINE — deterministic, network-free (NFR-01)"]
        N --> P["pricing<br/>(agent-verified rates)"]
        P --> R["rules: 9 detectors<br/>$-quantified findings"]
    end
    R --> REP["report / tokenomics<br/>artifacts"]
    REP --> S1["dashboards + drift"]
    REP --> S2["read API + JS SDK + MCP"]
    REP --> S3["Savings Statement<br/>(verified only, R-Q9)"]
    R --> AL["alerts — observe-only (X-02)"]
    L0["flywheel L0 labels"] -.->|"n-thresholds"| LAD["L1–L4 ladder 📋"]
    S1 --> L0
```

## Where truth lives (never guess, look here)

| Question | File |
|---|---|
| What do we build next? | `internal/QUEUE.md` (the ONLY work spine) |
| Is X shipped, and where's its test? | `04-TRACEABILITY.md` |
| Is the lifecycle complete? What's gated on what? | `internal/LIFECYCLE-MAP.md` |
| What was decided and why? | `STATUS.md` (append-only decision log) |
| How does a slice ship (DoD, gates)? | `09-SDLC.md` |
| Why is my bug happening? | `internal/DEBUGGING-PLAYBOOK.md` |

## Known-stale register

- `uml/` — 2 diagrams, both pre-platform-track → QUEUE candidate T-D2 (architect-gated).
