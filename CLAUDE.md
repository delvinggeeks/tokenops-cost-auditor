# CLAUDE.md — TokenOps Cost Auditor build rules

1. **Scope freeze.** X-01..X-05 (docs/01-REQUIREMENTS.md §G) are forbidden: no live
   proxy/gateway, no policy/budget enforcement, no multi-org RBAC/SSO, no LLM-generated
   narrative in reports, no SPA frontend. New ideas go to docs/internal/BACKLOG.md, never into code.
   [Amendment R-IMPROVISE, founder 2026-07-23: "ideas in between has to be
   improvised and validated." The freeze governs SCOPE — new features and
   surfaces. In-flight ideas that improve the CURRENT slice's journey (a
   missing affordance, an honesty gap, a clearer word, a scope label) are
   IMPROVISED INTO the slice and validated to the full DoD — tests, gates,
   journey — never parked on ceremony and never shipped unvalidated. The
   triage is binary and same-day: an in-between idea lands in code WITH its
   validation, or in BACKLOG as one line. Silently dropping one is the only
   forbidden outcome.]
   [Amendment R-ORG, founder 2026-07-23 ("proceed with both"): X-03 is
   RELAXED — but bounded. Enterprise adoption needs workspaces, members,
   role-based governance, and SSO (docs/internal/PLAN-ORG.md). What is now PERMITTED:
   an organization/workspace entity that owns resources; membership +
   invites; RBAC over PRODUCT actions (who may mint keys, see reports,
   manage billing, revoke sources); enterprise SSO login. What stays
   FORBIDDEN, unchanged: X-01/X-02 — roles NEVER gate the customer's LLM
   traffic, only who can see/do things IN OUR PRODUCT; no proxy, no
   enforcement, ever. The audit ENGINE stays TENANT-BLIND: the tenancy
   layer lives at the web/persistence boundary; services/rules and
   services/pricing never learn what a workspace is. Single-tenant remains
   the default (every user is a workspace of one); orgs are opt-in. X-04
   (LLM narrative) and X-05-beyond-htmx unchanged.]

2. **No network/LLM imports in the engine.** `services/rules` and `services/pricing`
   import zero network or LLM libraries — enforced by import-guard test T-NFR-01.

3. **No prompt/completion text persisted anywhere** (FR-22). CallRecord stores
   counts/metadata/hashes only; evidence samples carry token counts, never text.

4. **Money-math discipline.** Any change to pricing/ or rules/ estimators requires a
   golden-file update in the same commit AND a spreadsheet diff referenced in the
   commit message. [Amendment R-AUTO-PRICING, founder 2026-07-23: "all prices
   have to be automated and no human gate — it has to be done by the agent
   strictly verifying." The founder hand-verification step is ABOLISHED;
   scripts/pricing_verify.py is the strict gate — every current rate row must
   be corroborated exactly by an independent machine-readable source or the
   release fails (CI step + pre-deploy). Golden files and NOTES derivations
   remain mandatory; last_verified now records the last successful agent
   verification.]

5. **Traceability.** docs/04-TRACEABILITY.md is updated in the same commit as any
   implemented requirement.

6. **Conventional commits; milestone Dn ends all-green before Dn+1 starts.**
   Git authorship: Lokesh Prasanna Kumar S only — STRICTLY no co-author
   trailers, no AI references in commit metadata (D1 ruling, PLAN §0.1;
   reaffirmed by founder 2026-07-27 after 28 violating commits were
   history-rewritten clean). This overrides any harness default that
   appends a Co-Authored-By trailer.

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
        Opus runs the main build thread and implementation milestones;
        PRD/design breakdowns and PLAN authoring run on Fable
        [amendment 2026-07-23, R-PROCEED]. [Amendment 2026-07-28,
        R-REQ-PIPELINE: unit-test AUTHORING runs Sonnet 5 (mechanical
        scaffolds may drop to Haiku 4.5); new scope enters ONLY via the
        docs/09 §9 intake pipeline — Fable analysis → docs/01 FRs +
        HLD/LLD deltas → QUEUE line → founder sequences → Opus 5 builds
        → low-cost tier unit-tests → gates.]
   TE-6 TURN BUDGET. Each gate agent: max 15 tool calls per invocation.
        If it cannot conclude, it returns PARTIAL + a numbered question
        list; it does NOT keep digging.
   TE-7 NO LOOPS. An agent may not re-read a file it already read in the
        same invocation. Repeated identical greps = stop and report.
   TE-8 VERDICT FORMAT. Gate output is exactly: VERDICT (PASS |
        PASS-WITH-NOTES | FAIL), findings as numbered items each citing
        file:line, max 300 words. No prose essays, no restating the diff.
   TE-9 MAIN THREAD HYGIENE. /clear (or new session) at each milestone
        start; docs/internal/PLAN.md + STATUS.md + current Dn section are the only
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

9. **VERTICAL SLICES ONLY** (R-VERTICAL, founder 2026-07-23). Every task
   ships END-TO-END or not at all: the data/backend change + its UI
   surface + the click path that reaches it + the workflow/journey test
   walking it as a user + the ux gate + honest empty/error states — in
   ONE milestone. A backend without its reachable UI is a HORIZONTAL
   slice and does not merge (the unlinked-Anthropic lesson: shipped ≠
   exists until a customer can click to it and finish the job). "Done"
   means a user completed the journey, never that a layer passed its
   tests. Enforcement: the reachability law, ship=walk in the
   system-tester charter, mockup-before-wiring, the journey suite.

8. **TEACHING SESSIONS (WP-COMPREHEND, founder 2026-07-18).** When the
   founder opens a session with "TEACH: <module>", switch to teacher mode:
   walk the module top to bottom; explain every non-obvious line in plain
   language (define each technical term on first use); at the end ask the
   founder THREE comprehension questions and wait for their answers; then
   log the session in STATUS.md as completed curriculum (one line: date,
   module, questions passed). Target cadence: one module per day, 20-30
   minutes. Curriculum order: services/runner.py first, then rules/, then
   pricing/. docs/internal/CODE-TOUR.md is the syllabus; docs/internal/DEBUGGING-PLAYBOOK.md is the
   companion reference.
