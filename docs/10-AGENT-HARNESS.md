# Agent Harness & Token Economy — TokenOps build (v1.3)

Design goal: every SDLC role staffed by a specialist agent, at MINIMUM
token cost. Anti-goal: the 5M-token failure mode (agents exploring the
repo, re-reading files, looping on wrong assumptions).

## 1. Role -> agent mapping (9 human roles, 6 agents + main thread)

Main thread (Opus, you drive): orchestrator + builder. Writes code per
approved PLAN.md. All other agents are GATES, not builders.

| Requested role            | Agent            | Model  | When invoked |
|---------------------------|------------------|--------|--------------|
| Requirements engineer     | spec-guard       | Sonnet | milestone gate |
| Traceability owner        | spec-guard       | Sonnet | (same run)   |
| System designer           | architect        | Sonnet | milestone gate |
| EA / UML architect        | architect        | Sonnet | (same run; Mermaid on demand) |
| Designer / UX             | ux-reviewer      | Sonnet | D7-D8 only   |
| Cold reviewer             | cold-reviewer    | Sonnet | milestone gate |
| V&V engineer              | vv-engineer      | Sonnet | milestone gate |
| System integration        | ops-engineer     | Sonnet | D1, D10, D13 |
| CI/CD engineer            | ops-engineer     | Sonnet | (same runs)  |
| Observability engineer    | ops-engineer     | Sonnet | (same runs)  |
| SaaS subsystems / ops     | ops-engineer     | Sonnet | (same runs)  |

Rationale for consolidation: each extra agent costs a full context spin-
up. Roles sharing the same inputs (diff + same spec docs) share an agent.
Six specialists at milestone gates beats eleven agents per prompt by an
order of magnitude in tokens, with zero review-quality loss.

## 2. Token economy rules (CLAUDE.md-enforced)

TE-1 GATES AT MILESTONES ONLY. Agents run at the end of each Dn
     milestone, never per-prompt, never per-file. (Lesson: per-prompt
     blocking hooks burn tokens and stall flow.)
TE-2 DIFF-ONLY CONTEXT. Every gate agent receives: (a) git diff of the
     milestone branch vs main, (b) STATUS.md, (c) ONLY the spec sections
     named in its charter. Agents are FORBIDDEN from repo-wide reads.
TE-3 GREP BEFORE READ. Any file access = targeted grep/offset read.
     Reading a whole file >300 lines requires stating why in output.
TE-4 STATUS.md IS SHARED MEMORY. One paragraph per milestone: decisions,
     open questions, file map delta. Agents read it INSTEAD of exploring.
TE-5 MODEL TIERING. Gate agents run Sonnet (set in agent frontmatter).
     Opus is reserved for the main build thread and PLAN.md authoring.
TE-6 TURN BUDGET. Each gate agent: max 15 tool calls per invocation.
     If it cannot conclude, it returns PARTIAL + a numbered question
     list; it does NOT keep digging.
TE-7 NO LOOPS. An agent may not re-read a file it already read in the
     same invocation. Repeated identical greps = stop and report.
TE-8 VERDICT FORMAT. Gate output is exactly: VERDICT (PASS |
     PASS-WITH-NOTES | FAIL), findings as numbered items each citing
     file:line, max 300 words. No prose essays, no restating the diff.
TE-9 MAIN THREAD HYGIENE. /clear (or new session) at each milestone
     start; PLAN.md + STATUS.md + current Dn section are the only
     carry-over context. Never carry a full milestone's transcript.
TE-10 FAIL FAST. A FAIL verdict stops the milestone; fixes happen in
     the main thread; the gate re-runs on the NEW diff only.
TE-11 PINNED TOOLCHAIN ONLY. [amendment 2026-07-17, R-TOOLCHAIN] Any
     gate check that executes, compiles, lints, or type-checks code
     MUST run through the project toolchain (`uv run ...` against the
     pinned interpreter), never the sandbox/system python. A finding
     produced by any other interpreter is invalid by definition. When
     a reviewer and the main thread disagree on a toolchain-dependent
     fact, the pinned-toolchain reproduction is authoritative; the
     resolution is recorded in STATUS.md.

Expected cost profile: gate sweep (4 agents x Sonnet x diff-only)
~ 50-150K tokens per milestone; 14-day build total well under one of
the 5M-token incidents this design exists to prevent.

## 3. Gate schedule

| Milestone | Gates run (in order) |
|-----------|----------------------|
| D1 scaffold | ops-engineer, spec-guard |
| D2-D3 ingest+pricing | vv-engineer, cold-reviewer |
| D4-D5 detectors | vv-engineer, spec-guard, cold-reviewer |
| D6-D7 runner+report | architect, vv-engineer, ux-reviewer(D7) |
| D8-D9 auth+payments+landing | ux-reviewer, cold-reviewer, spec-guard |
| D10 lifecycle+ops | ops-engineer, vv-engineer |
| D11-D12 UAT | vv-engineer (UAT evidence check) |
| D13 deploy | ops-engineer (runbook conformance) |
| D14 launch | spec-guard (final traceability sweep) |

## 4. Agent charters (files in .claude/agents/)

spec-guard: verifies diff implements only FR/NFR scope; X-01..X-05 not
violated; traceability matrix updated; FR-22 privacy invariant holds.
Reads: diff, 01-REQUIREMENTS.md, 04-TRACEABILITY.md.

architect: verifies package boundaries per 03-LLD.md section 1; ADR
conformance (02-HLD.md section 5); no cross-layer imports; on request
emits/updates docs/uml/*.mmd (Mermaid component + sequence diagrams) —
generated at D6 and D13 only, not continuously.
Reads: diff, 02-HLD.md, 03-LLD.md sections 1-2.

ux-reviewer: landing page (clarity of value prop, FR-23 policy string,
mobile rendering, one-CTA rule), report PDF/web (executive readability:
savings number visible in 5 seconds, chart legibility, non-technical
CTO test). Reads: diff of templates/, 00-PRD.md section 4, rendered
screenshots if provided.

cold-reviewer: fresh-context adversarial review of the diff — logic
errors, edge cases, silent failure paths, dead code, misleading names.
Explicitly ignores style (ruff owns style). Reads: diff only + STATUS.md.

vv-engineer: verifies every changed module has tests per 05-TEST-PLAN
IDs; golden numbers updated with spreadsheet diff when money math
changed; coverage gates met; runs the test suite; false-positive guard
(clean fixture) still silent. Reads: diff, 05-TEST-PLAN.md,
04-TRACEABILITY.md test column.

ops-engineer: compose/CI/Caddy/backup/healthz conformance to
06-OPS-RUNBOOK.md; secrets not in repo; image builds; migration
additive-only policy; deploy-drill checklist. Reads: diff of infra
files, 06-OPS-RUNBOOK.md.

## 5. Failure-mode kill switches (the 5M-token insurance)

K-1 Any agent exceeding its 15-tool-call budget self-terminates with
    PARTIAL verdict.
K-2 Main thread rule: if a fix attempt fails twice on the same test,
    STOP — write the failing state to STATUS.md and ask the founder.
    Never enter attempt-loop #3 unattended.
K-3 Session token sanity: at each milestone boundary, note context size;
    if a single Dn session exceeds ~200K tokens of accumulated context,
    /clear and reload minimal state (TE-9).
K-4 No agent may spawn another agent.
