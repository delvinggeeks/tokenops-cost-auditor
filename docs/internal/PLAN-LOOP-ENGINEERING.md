# PLAN-LOOP-ENGINEERING — the autonomous SDLC loop

**Status: RULED (founder 2026-07-24; deploy governance amended 2026-07-25).**
"Any bugs or new requirements has to be clearly PR raised, implement, build,
test and merge cleanly without any human gate, following clear discipline of
vertical slices … the entire SDLC cycle in a loop, i.e. loop engineering."
Founder decisions (AskUserQuestion 2026-07-24): **fully autonomous** driver ·
**continuous deployment to staging, founder-gated promotion to prod** ·
**GitHub Issues** intake. The 2026-07-25 ruling reversed the original
auto-deploy-to-prod design: staging auto-deploys on every merge; production
ships only on a manual `workflow_dispatch` the founder triggers after
reviewing the rendered staging pages — authority is `docs/09-SDLC.md` §5.
Authorship stays the founder's, mechanically enforced (no AI header/footer
anywhere — LE-1, shipped).

## 0. What this is

A self-driving software factory: a GitHub Issue (a bug or requirement) enters and
comes out as a change implemented, gated, merged, and auto-deployed to
staging — with **no human gate** from Issue to staging. The machine gates
(CI + the adversarial agent gate round) are the ENTIRE quality and safety
authority up to that point; there is no human reviewer. The one deliberate
human gate in the loop is **production promotion**: the founder reviews the
rendered staging pages, then triggers prod via manual `workflow_dispatch`
(`docs/09-SDLC.md` §5, ruling 2026-07-25). This is a deliberate, founder-ruled
tradeoff — its honest risk and its containment are §3.

## 1. The loop (one iteration)

```
① INTAKE      pick the top `loop:ready` GitHub Issue (acceptance criteria in body)
② SLICE       decompose into VERTICAL slices (R-VERTICAL) — each with DoD
③ BRANCH      one slice = one branch off main
④ IMPLEMENT   end-to-end: data/backend + UI + click-path + journey test
⑤ BUILD+TEST  CI (authorship · ruff · mypy · pytest · coverage · pricing-verify ·
              docs-drift)  ▸ then the agent GATE ROUND (cold · spec · vv ·
              system-tester · ux-when-a-surface-changed), verdicts posted to the PR
⑥ PR          raised: template + gate verdicts + traceability, links the Issue
⑦ MERGE       AUTO-MERGE the moment every required check is green — no human click
⑧ DEPLOY      on merge to main: auto-deploy to STAGING (backup → provision →
              external smoke → auto-rollback); PRODUCTION ships only on a
              founder-triggered manual `workflow_dispatch` after staging review
⑨ VERIFY+LOOP staging smoke green ⇒ close the Issue, update STATUS/traceability, next Issue
```

## 2. The build — vertical slices (each its own branch → PR, per the discipline)

- **LE-1 — Clean-authorship hard gate.** [SHIPPED — branch `chore-authorship-guard`]
  `scripts/check_authorship.py` fails any commit range with a non-founder author,
  an anthropic email, or an attribution trailer/footer; wired into `ci.yml` as a
  parallel required check. AC: a bad author or `Co-Authored-By` fails CI; honest
  prose that merely names the tools passes. DoD met (tested both ways, self-verifies).

- **LE-2 — Continuous deployment (REDEFINED by founder ruling 2026-07-25:
  staging-auto, prod founder-gated — see `docs/09-SDLC.md` §5, the
  authority for this slice).** `deploy.yml` also triggers on `push` to
  `main`; the gate job re-runs the full chain + `pricing_verify.py` on the
  merged SHA; deploy does backup → provision → external smoke → auto-rollback
  to the prior tag; the deploy tag is derived automatically (version file or
  `vYYYY.MM.DD-<sha>`). A merge to `main` **auto-deploys to STAGING only**;
  `deploy-production` is gated `if: github.event_name == 'workflow_dispatch'`
  — the founder triggers it manually after reviewing the rendered staging
  pages. **Prod never auto-ships.** AC: a merge to main auto-deploys to
  staging; a failed gate or smoke blocks/rolls back and never leaves
  staging or prod half-updated; prod only ships on a manual dispatch. DoD:
  workflow validated on a dry-run/staging path; runbook §2 updated.
  FOUNDER-LANE: DEPLOY_HOST/DOMAIN/SSH_KEY secrets; HELD pending those
  secrets (per `docs/09-SDLC.md` §6).

- **LE-3 — Auto-merge on green.** Branch protection on `main` requires the full
  check set (authorship · lint · type · test · coverage · docs · gate-round);
  a workflow runs `gh pr merge --auto --squash` on every loop PR so it merges the
  instant checks pass. AC: a fully-green PR merges with no human action; any red
  or missing required check blocks it forever. DoD: protection config scripted;
  a red PR proven un-mergeable.

- **LE-4 — Gate round in CI (the automated reviewer).** A GitHub Action invokes
  the agent gate round (cold/spec/vv/system-tester/ux) on each PR via Claude Code
  headless, posts the TE-8 verdicts as a PR check, and FAILS the check on any FAIL
  verdict — this required check is what replaces the human reviewer. AC: every PR
  gets verdicts; a FAIL blocks auto-merge; a PASS/PWN lets it through. DoD: the
  action + a synthetic FAIL proven to block. (Hardest slice — headless agents in
  CI with a token budget; degrade to "block on error" so a broken gate never
  auto-merges.)

- **LE-5 — Autonomous issue driver.** A scheduled Claude Code routine (or an
  issue-labeled trigger) that picks the top `loop:ready` Issue, slices it (VERTICAL
  + DoD), and runs ②–⑥ per slice, then closes the Issue on ⑨. An Issue template
  captures acceptance criteria + DoD; labels drive state (`loop:ready` →
  `loop:in-progress` → closed); priority orders the queue. AC: labeling an Issue
  `loop:ready` results — with no human step — in the change implemented, PR'd,
  gated, merged, deployed, and the Issue closed. DoD: driver + template + labels +
  a **kill-switch** label/flag that halts intake.

- **LE-6 — Observability, kill-switch, scale.** A loop status surface (what's in
  flight, cycle time, pass rate), the `loop:paused` kill-switch honored everywhere,
  and a runbook so new requirement TYPES slot in without rework. AC: the loop's
  state is visible; pausing stops new work within one cycle; adding a requirement
  is "open an Issue," nothing more. DoD: status + runbook + pause proven.

Bootstrap order: LE-1 (done) → LE-2 → LE-3 → LE-4 → LE-5 → LE-6. LE-1..4 are built
by hand via the branch→PR flow (the loop can't build itself yet); once LE-1..5 are
live the loop **self-drives** every subsequent Issue, including LE-6 and all
product work (O-1b-1/2/3 onward become Issues the loop implements).

## 3. The honest risk + its containment (no-human-gate to staging; founder-gated prod)

Fully autonomous merge + staging deploy means: **a defect that passes every gate
ships to staging automatically.** There is no human catch before staging.
Production is different: it ships only on the founder's manual
`workflow_dispatch` after reviewing the rendered staging pages
(`docs/09-SDLC.md` §5), so a defect reaching prod additionally requires that
review to miss it. Containment, all machine-enforced up to staging, plus the
founder review before prod:
- The **agent gate round** (LE-4) is an ADVERSARIAL reviewer — cold-reviewer hunts
  the bug the tests can't (the O-1a sweep proved this catches missed-site classes);
  a FAIL blocks merge.
- **CI laws**: authorship, FR-22 (no text), X-scope (no proxy/enforcement/RBAC-leak),
  the money law (`pricing_verify.py` — a wrong rate FAILS the build), coverage.
- **Deploy safety**: pre-deploy backup, external smoke, **auto-rollback** to the
  prior tag on any smoke failure — staging and prod both self-heal.
- **Founder gate on prod**: the rendered staging pages are reviewed before the
  manual dispatch; nothing reaches prod unattended.
- **Kill-switch** (LE-6): `loop:paused` halts intake; a human can always stop it.
- **Vertical slices**: small, reversible changes — a bad slice is one revert.
The residual risk (a defect that fools every gate, passes staging smoke, AND
survives founder review) is bounded by backup + rollback + revert, never
unrecoverable.

## 4. Cross-cutting laws the loop never breaks

Clean authorship (LE-1) · vertical slices (R-VERTICAL) · FR-22 · X-01..X-05 scope ·
the money law · traceability (rule 5) · reachability · honest empty/error states.
Every one is a CI or gate check — the loop is DEFINED by these gates, so it
cannot ship a change that violates them.
