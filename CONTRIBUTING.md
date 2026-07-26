# Contributing

Internal contributor guide. Access is limited to authorized team members
(private, proprietary — see [LICENSE](LICENSE)).

## Setup

See the [README quickstart](README.md#quickstart-local-development). Everything
runs through `uv` (the pinned toolchain) — never the system Python.

## The one rule that governs everything: vertical slices

Every change ships **end-to-end or not at all** — the data/backend change **+**
its UI surface **+** the click-path that reaches it **+** a test that walks it
**+** honest empty/error states, in one slice. A backend without its reachable
UI does not merge. Small, reversible slices; one slice = one branch = one PR.

## The non-negotiable laws (all machine-checked in CI)

- **Authorship** — every commit is authored by the repository owner, with **no
  AI attribution trailer or footer** anywhere. Enforced by
  `scripts/check_authorship.py` (a required CI gate).
- **Engine stays tenant-blind** — `services/rules` and `services/pricing` must
  never import network/LLM libraries or learn about users/workspaces (`T-NFR-01`).
- **No prompt/completion text is ever persisted** (FR-22) — counts, ids, and
  user-safe words only.
- **Money law** — any pricing/estimator change carries golden-file updates in the
  same commit; `scripts/pricing_verify.py` must exit 0 (a wrong rate fails CI).
- **Traceability** — `docs/04-TRACEABILITY.md` is updated in the same commit as
  any implemented requirement.
- **Scope freeze** — the `X-01..X-05` boundaries in `docs/01-REQUIREMENTS.md`
  hold; new ideas go to `docs/internal/BACKLOG.md`, not into code.

## Workflow

```
branch off main  →  implement the slice  →  open a PR
      →  CI (authorship · ruff · mypy · pytest+coverage · pricing-verify · docs)
      →  adversarial gate review  →  squash-merge (green only; main is protected)
      →  auto-promote: deploy → STAGING → smoke → PRODUCTION
```

Before pushing, run the exact CI commands locally (not partial ones):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q -m "not perf"
uv run python scripts/pricing_verify.py
```

## Commit style

Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`, …). One coherent concern
per commit. No AI/co-author trailers (the authorship gate rejects them).

## The autonomous loop

Some cards are built by an autonomous agent instead of a person. To hand a
task to it:

1. Open a GitHub Issue using the **loop-task** template
   (`.github/ISSUE_TEMPLATE/loop-task.yml`) — it asks for the user-facing
   goal, the acceptance criteria, and what's out of scope.
2. Add the **`loop:ready`** label. An agent picks it up, branches off `main`,
   builds the slice end-to-end (code + tests + docs), and opens a PR.
3. The **gate round** (the same adversarial review a human-built card gets)
   reviews the PR's diff, and on a green verdict the PR **auto-merges**.
4. Merging to `main` auto-deploys to **staging**. **Production is still
   founder-gated** — a manual promotion after reviewing staging — the loop
   never ships to prod on its own.

A `loop:ready` issue must meet the same discipline as any other card:

- It is a **modular vertical slice** — one end-to-end change a user can
  reach, not a horizontal layer.
- It states **explicit acceptance criteria** (the user job, the surfaces
  touched, the tests that prove it, what's out of scope).
- It stays inside the CI laws the gate round enforces: the **authorship**
  law (no AI/co-author trailers), the **scope freeze** (`X-01..X-05`), the
  **FR-22** privacy invariant (no prompt/completion text persisted), the
  **engine boundary** (`T-NFR-01` — `services/rules`/`services/pricing` stay
  network/LLM-free), and a **green pinned toolchain**
  (`uv run ruff check . && uv run ruff format . && uv run mypy && uv run pytest -m 'not perf'`).

**Kill-switch.** To halt all auto-merge instantly (loop-built or
human-built):

```bash
gh variable set LOOP_PAUSED --body true    # halt
gh variable set LOOP_PAUSED --body false   # resume
```

**Status.** To see whether the loop is paused, whether auto-merge and the
gate round are enforced, which PRs are armed, and the recent gate-round
pass rate:

```bash
uv run python scripts/loop_status.py
```

## More

- Architecture & methods: [`docs/internal/PLATFORM.md`](docs/internal/PLATFORM.md)
- Requirements & scope: [`docs/01-REQUIREMENTS.md`](docs/01-REQUIREMENTS.md)
- Ops & deploy: [`docs/06-OPS-RUNBOOK.md`](docs/06-OPS-RUNBOOK.md)
- Current state / decisions: [`STATUS.md`](STATUS.md)
