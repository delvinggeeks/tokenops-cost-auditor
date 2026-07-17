# CLAUDE.md — TokenOps Cost Auditor build rules

1. **Scope freeze.** X-01..X-05 (docs/01-REQUIREMENTS.md §G) are forbidden: no live
   proxy/gateway, no policy/budget enforcement, no multi-org RBAC/SSO, no LLM-generated
   narrative in reports, no SPA frontend. New ideas go to BACKLOG.md, never into code.

2. **No network/LLM imports in the engine.** `services/rules` and `services/pricing`
   import zero network or LLM libraries — enforced by import-guard test T-NFR-01.

3. **No prompt/completion text persisted anywhere** (FR-22). CallRecord stores
   counts/metadata/hashes only; evidence samples carry token counts, never text.

4. **Money-math discipline.** Any change to pricing/ or rules/ estimators requires a
   golden-file update in the same commit AND a spreadsheet diff referenced in the
   commit message.

5. **Traceability.** docs/04-TRACEABILITY.md is updated in the same commit as any
   implemented requirement.

6. **Conventional commits; milestone Dn ends all-green before Dn+1 starts.**

7. **TOKEN ECONOMY** — copied verbatim from docs/10-AGENT-HARNESS.md §2 and §5:

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

   K-1 Any agent exceeding its 15-tool-call budget self-terminates with
       PARTIAL verdict.
   K-2 Main thread rule: if a fix attempt fails twice on the same test,
       STOP — write the failing state to STATUS.md and ask the founder.
       Never enter attempt-loop #3 unattended.
   K-3 Session token sanity: at each milestone boundary, note context size;
       if a single Dn session exceeds ~200K tokens of accumulated context,
       /clear and reload minimal state (TE-9).
   K-4 No agent may spawn another agent.
