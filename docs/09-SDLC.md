# 09 — The Development Process (single source of truth for HOW)

**Purpose.** ONE authoritative definition of how every unit of work is built, verified,
and shipped — so the process is followed the same way for every requirement, new or old.
This is the counterpart to `docs/internal/ROADMAP.md` (the "what"). Consolidated + RECONCILED
2026-07-25 from the process rules previously scattered across CLAUDE.md, KANBAN.md,
PLAN-LOOP-ENGINEERING.md, 10-AGENT-HARNESS.md, PLAN.md §0, 05-TEST-PLAN, 06-OPS-RUNBOOK,
CONTRIBUTING.md, DEVELOPMENT.md.

**Authority.** Where this doc and another disagree, THIS doc wins for process; the others
remain authoritative for their own domain (test IDs → 05; runbook steps → 06; gate charters
→ .claude/agents/). Contradictions this doc resolves are listed in §8.

---

## 1. The card lifecycle (states, entry/exit, WIP)

Every unit of work is a CARD (a vertical slice). It moves through fixed states; a card may
NOT enter a state until its entry criteria hold. **WIP = 1** in-flight card at a time (one
branch, one PR) unless the founder rules otherwise — no starting a second slice before the
first is Done.

| State | Entry criteria (must hold to ENTER) | Who moves it |
|-------|-------------------------------------|--------------|
| **Backlog** | An idea/requirement exists (ROADMAP §5 or a founder ask) | anyone |
| **Ready** | **Acceptance criteria written** (§2) + it is a true vertical slice + it is next per ROADMAP §3 / founder order | founder confirms scope |
| **In-progress** | Branch off `main`; (for a NEW UI surface) a mockup exists + passed ux review (mockup-before-wiring) | builder |
| **In-review** | Implementation complete to the DoD (§3); CI green; the gate round run (§4) | builder → gates |
| **On staging** | Merged to `main` → auto-deployed to staging (§5) | pipeline |
| **Done** | Founder reviewed the rendered pages on staging → **promoted to prod** (§5); STATUS paragraph + traceability written | founder promotes |

**"Done" means a user can finish the job in production** — not that a layer passed its tests
(R-VERTICAL). A backend without its reachable UI + journey test is NOT Done.

---

## 2. Acceptance criteria — the REQUIRED entry gate to "Ready"

No card is built until its acceptance criteria are written down (in the ROADMAP card, the
GitHub Issue once LE-5 ships, or the PR description). Acceptance criteria state, concretely:

1. **The user job** — what a user can do end-to-end when this is Done (the click path).
2. **The surfaces** — which page(s)/route(s) change, and their honest empty/error states.
3. **The measurable checks** — the specific assertions/tests that prove it (journey test +
   unit tests + any golden).
4. **Out of scope** — what this slice deliberately does NOT do (parked to ROADMAP §5).
5. **Which gates apply** (§4) and any money-math / migration / FR-22 implications.

If acceptance criteria cannot be written, the card is too big → split it into smaller vertical
slices, each with its own criteria. Skipping this step is the root cause of reactive, ad-hoc
work; it is not optional.

---

## 3. Definition of Done — the canonical checklist

A card is Done only when EVERY item holds. Each item names the check that OWNS it.

| # | DoD item | Owned by (the check) |
|---|----------|----------------------|
| 1 | Acceptance criteria met (§2) — the user job works end-to-end | system-tester + journey suite |
| 2 | R-VERTICAL: UI + click path + journey test + honest empty/error states | system-tester + `tests/test_journeys.py` + `TestDeclaredEqualsReachable` |
| 3 | Whole-surface experience holds (no cluttered/duplicated/stale-unlabelled pages) | `tests/test_experience_walkthrough.py` |
| 4 | Unit/integration tests per `docs/05-TEST-PLAN.md` IDs; changed module has tests | vv-engineer + `pytest` |
| 5 | Coverage: ≥85% services, 100% on money files (coster.py, findings.py) | `scripts/coverage_gate.py` |
| 6 | Money-math: golden updated in the SAME commit + derivation in NOTES/commit msg | vv-engineer (review) + `pricing_verify.py` (rates) |
| 7 | FR-22: counts/metadata only, no prompt/completion text persisted | spec-guard + `T-RUL-EV-01` |
| 8 | Scope: X-01..X-05 honored; new ideas parked to ROADMAP §5 (R-IMPROVISE triage) | spec-guard |
| 9 | Engine purity: `services/rules`+`services/pricing` import no network/LLM | `T-NFR-01` |
| 10 | Traceability row added/updated in the SAME commit | spec-guard (review) |
| 11 | STATUS.md paragraph written | (author discipline; checked at PR) |
| 12 | Conventional commit; NO AI/co-author trailers | `scripts/check_authorship.py` |
| 13 | Gate round run, all verdicts PASS or PASS-WITH-NOTES-then-resolved (§4) | the 5 gate agents |
| 14 | ux mockup-before-wiring for a NEW surface | ux-reviewer |
| 15 | ≤3-day slice | author discipline |

**PASS-WITH-NOTES rule (resolved here):** a card is NOT Done while any gate note is
open. Every note is either fixed (with a test) or explicitly parked to ROADMAP §5 with the
founder's ok — same-day, binary, per R-IMPROVISE. Silently dropping a note is forbidden.

---

## 4. The gate round — WHICH gates, per card (replaces the obsolete D1–D14 schedule)

The old `10-AGENT-HARNESS.md §3` schedule is keyed to a one-time D1–D14 build and is
**obsolete**. In the continuous-card era the rule is: **the gate round runs once per card,
at In-review (on the card's diff), before merge.** Gates by card type:

| Gate | Runs on | Purpose |
|------|---------|---------|
| **cold-reviewer** | every card | adversarial logic/edge-case/silent-failure hunt |
| **spec-guard** | every card | scope (X-01..05), FR-22, traceability, requirement conformance |
| **vv-engineer** | every card | tests per 05, coverage, money-math golden discipline, false-positive guard |
| **system-tester** | every card | the assembled product walked as a user; reachability; ship=walk |
| **ux-reviewer** | any card touching a customer-facing surface | 3-second rule, plain-language, honesty, mockup-before-wiring |
| **architect** | cards changing package boundaries / cross-cutting structure | HLD/LLD conformance, UML |
| **ops-engineer** | cards changing CI/deploy/compose/secrets/observability | runbook conformance |

**Discipline (unchanged):** TE-2 diff-only context (diff + STATUS + charter docs); TE-6 ≤15
tool calls → else PARTIAL; **TE-8 verdict format** (`VERDICT (PASS|PASS-WITH-NOTES|FAIL)`,
numbered findings citing `file:line`, ≤300 words); TE-10 a FAIL stops the card, fix in the
main thread, re-run the failed gate on the NEW diff; TE-11 pinned toolchain only. K-2: a fix
that fails twice on the same test → STOP, write STATUS, ask the founder (never attempt-loop #3).

---

## 5. CI + deploy — the RECONCILED pipeline (this is the current reality)

**CI (`ci.yml`, on `pull_request`):** authorship · ruff check + format · mypy · pytest+coverage
(incl. the journey + experience gates) · coverage_gate · pricing_age (warn) · **pricing_verify
(hard fail)** · docs-drift (openapi/self-audit/mkdocs strict) · image build. `main` is NOT
re-run here (CI-once cost rule); it is validated by the deploy `gate` job.

**Deploy (`deploy.yml`) — staging-auto, prod founder-gated (founder ruling 2026-07-25):**
- Every merge to `main` → `gate` (full chain on the merged SHA) → **auto-deploy to STAGING** →
  smoke. Staging always mirrors main.
- **Production ships ONLY on a manual `workflow_dispatch`** the founder triggers AFTER
  reviewing the rendered pages on staging. `deploy-production` is `if:
  github.event_name == 'workflow_dispatch'`, backup → provision → external smoke →
  auto-rollback to the prior `RELEASE_TAG` on failure. **Prod never auto-ships.**
- The **experience gate** (`tests/test_experience_walkthrough.py`) runs in both CI and the
  deploy `gate` job, so emergent whole-surface regressions fail BEFORE staging.

**Why a manual prod gate (the "why are these reaching prod?" ruling):** a `healthz` smoke is
not a review; emergent, real-data UX issues only show on the rendered pages. The founder (or a
future automated rendered-surface review) looks at staging before prod. This SUPERSEDES the
"continuous deploy to prod, no human gate" language still present in PLAN-LOOP-ENGINEERING,
OPS-RUNBOOK §10, CONTRIBUTING, and DEVELOPMENT — those are being amended to match (§8).

---

## 6. Loop engineering — HONEST status (defined vs built)

The autonomous loop (`PLAN-LOOP-ENGINEERING.md` LE-1..6) is mostly DEFINED but NOT BUILT.
Today the SDLC is a **well-gated, human-driven** flow — not a self-driving factory. Do not
assume automation that does not exist:

| Stage | Defined | Reality today |
|-------|---------|---------------|
| LE-1 authorship gate | hard CI gate | **SHIPPED** (check_authorship in CI) |
| LE-2 continuous deploy | auto-deploy on merge | **PARTIAL + REDEFINED** (staging-auto; prod manual) + **HELD on founder DEPLOY_* secrets** |
| LE-3 auto-merge on green | `gh pr merge --auto` | **SHIPPED 2026-07-26** — `.github/workflows/auto-merge.yml` arms GitHub NATIVE auto-merge on any PR labelled `auto-merge` (branch protection is the gate). ACTIVATE: enable "Allow auto-merge" in repo Settings (one toggle). Label-gated until LE-6's kill-switch allows default-on. |
| LE-4 gate round in CI | headless agents fail a PR check | **SHIPPED 2026-07-25, VALIDATED LIVE** (PR #25) — `scripts/gate_round.py` + `.github/workflows/gate-round.yml` run the gate agents headless on the founder's subscription and fail the check on any FAIL/NO-VERDICT. To ENFORCE at merge: add `gate-round` to branch-protection required checks (currently advisory — authorship/lint/type/test/docs are required, gate-round is not). |
| LE-5 autonomous issue driver | GitHub Issues + `loop:*` labels + scheduler | **NOT BUILT** — intake is the human "proceed <id>" convention |
| LE-6 observability + kill-switch | loop status + `loop:paused` | **SHIPPED 2026-07-26** — kill-switch: the `LOOP_PAUSED` repo variable (`gh variable set LOOP_PAUSED --body true`) halts ALL auto-merge instantly, honored in auto-merge.yml's guard. Observability: `scripts/loop_status.py` reports paused / auto-merge / gate-round-required / armed-PRs / gate-round pass rate in one screen. |

**Consequence:** the process is enforced by CI (correctness) + human discipline (everything
else). Until LE-4 ships, the human-run gate round is load-bearing — so it must be run for
EVERY card, not skipped. Building LE-3/LE-4/LE-5/LE-6 (in that order, per PLAN-LOOP) is what
turns "followed by discipline" into "enforced by machine"; each is its own vertical slice on
the ROADMAP.

---

## 7. Change control (unchanged, restated for one place)

- New scope/surfaces are rejected by default → parked in `docs/internal/BACKLOG.md` /
  ROADMAP §5. Promotion needs a founder-written amendment in `docs/00-PRD.md` (PRD §10).
- R-IMPROVISE: an in-flight idea that improves the CURRENT card's journey is improvised INTO
  the card WITH full DoD validation, or parked as one BACKLOG line — same-day, binary.
- X-01..X-05 scope freeze (X-03 relaxed-bounded by R-ORG). Engine stays tenant-blind.

---

## 8. Reconciliations (contradictions this doc resolves)

1. **Deploy governance.** Prod is FOUNDER-GATED manual promotion after staging review (§5),
   NOT auto-deploy. PLAN-LOOP-ENGINEERING §"LE-2/flow", OPS-RUNBOOK §10 step 5, CONTRIBUTING,
   and DEVELOPMENT deploy diagrams are being amended to this; the `loop-engineering-model`
   memory ("no human gate") is stale and superseded.
2. **Gate schedule.** The D1–D14 milestone table is obsolete; gates run per-card per §4.
   system-tester runs on EVERY card (it was missing from the old table).
3. **PLAN authoring model.** Fable (R-PROCEED), not Opus — the 10-AGENT-HARNESS §2 TE-5 body
   is stale; CLAUDE.md rule 7's amended version is correct.
4. **Pricing verification.** AGENT-verified via `pricing_verify.py` (R-AUTO-PRICING) — the
   human "founder-verified golden rows before merge" wording in KANBAN is stale.
5. **"all-green".** Means: the full pinned `pytest` suite passes + coverage gate passes;
   PASS-WITH-NOTES is allowed at a gate only if every note is resolved before Done (§3).
6. **Enforcement honesty.** Traceability "same-commit" and money-math "spreadsheet-diff in
   commit" are REVIEW-enforced today (no CI script yet), not machine-checked — a CI
   traceability check is a ROADMAP item. Don't claim machine-checked where it's review-only.
