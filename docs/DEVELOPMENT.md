# Development guide

Everything a developer needs to go from a fresh clone to a running app, and
from a code change to a merged, deployed slice. The [README](../README.md) has
the 30-second version; this is the full walkthrough. The rules that govern
*how* changes ship live in [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 1. Prerequisites

Install these once. Everything else is pulled by `uv`.

| Tool | Why | Install |
|---|---|---|
| [`uv`](https://docs.astral.sh/uv/) | The **pinned** Python toolchain — runs the interpreter, deps, tests, lint, types. Never use system Python. | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Docker](https://docs.docker.com/engine/install/) + Compose v2 | Postgres locally, and the full app+db+Caddy stack | platform installer |
| `git` | version control | platform installer |

You do **not** install Python yourself — `uv` reads [`.python-version`](../.python-version) and fetches the exact interpreter the project pins.

---

## 2. Set up your environment (step by step)

```bash
# 1. Clone
git clone <repo-url> && cd tokenops-cost-auditor

# 2. Install all dependencies (including optional extras like obs/sentry)
uv sync --all-extras

# 3. Create your local config from the template
cp .env.example .env
#    Blank values in .env.example fall back to safe in-code defaults, so a
#    fresh .env boots as-is. Fill secrets only when you need that surface
#    (payments, mail, OAuth) — see the key groups in .env.example.

# 4. Start Postgres (the only service the app strictly needs to run locally)
docker compose up -d postgres

# 5. Apply database migrations
uv run alembic upgrade head

# 6. Run the app with live reload
uv run uvicorn tokenops_cost_auditor.main:app --reload
#    -> http://localhost:8000
```

Prefer the whole stack (app + Postgres + Caddy) in containers instead of steps 4–6?

```bash
docker compose up -d --build      # serves via Caddy; app on the compose network
```

### About `.env`
`.env.example` is the source of truth for **every** config key (a test enforces
that — `tests/test_smoke.py::test_env_example_complete`). Keys are grouped:
Core, Payments (FR-18), Mail (FR-20), Observability, Detector thresholds,
Plans/pricing, and signup federation (Google/Microsoft OAuth). Optional keys
left blank use their default; env-gated surfaces (payments, SMTP, Sentry,
OAuth buttons) simply stay off until their keys are set.

> **Gotcha (regression-pinned):** a blank optional value must be treated as
> *unset*, not as an empty string — otherwise a fresh deploy crash-loops on
> `""` where a float/int is expected. `config.py` handles this; the pin is
> `tests/test_smoke.py::test_env_example_boots_a_fresh_deploy`.

---

## 3. Verify it works

```bash
curl -s localhost:8000/healthz          # -> {"ok":true,"db":true,...}
open http://localhost:8000              # landing page renders
```

---

## 4. The daily dev loop

Run the **exact** CI commands locally before you push — not partial ones (CI
runs the full set and will catch what a partial run misses):

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                           # types
uv run pytest -q -m "not perf"                        # tests (skip slow perf)
uv run python scripts/pricing_verify.py               # money-math gate
```

Shortcuts (see [`Makefile`](../Makefile)): `make test`, `make lint`. Preview
harness for the report UI: `make preview`, `make preview-empty`, `make preview-reset`.

---

## 5. Project structure

```
tokenops-cost-auditor/
├── README  LICENSE  CHANGELOG  CONTRIBUTING  SECURITY   # front door
├── pyproject.toml  uv.lock  .python-version  Makefile   # build / toolchain
├── Dockerfile  docker-compose.yml  Caddyfile  .env.example   # run
├── src/tokenops_cost_auditor/          # application code (see below)
├── tests/                              # pytest suite (~1:1 with code)
├── docs/                               # architecture, requirements, this guide
│   ├── 00-PRD … 13-*  04-TRACEABILITY  # numbered specs + the traceability matrix
│   ├── DEVELOPMENT.md                  # you are here
│   ├── design/                         # design-system source + specs + evidence
│   └── internal/                       # plans, runbooks, STATUS history, launch
├── docs-site/                          # public documentation site (mkdocs)
├── deploy/                             # Terraform (Hetzner) + provisioning
├── scripts/                            # provisioning, pricing verify, doc gen
└── .github/workflows/                  # CI + staging→prod deploy
```

Inside the application:

```
src/tokenops_cost_auditor/
├── web/          FastAPI routes + htmx/Jinja templates (dashboard, sources, runs, reports, settings)
├── api/          machine surfaces — /api/v1/ingest (upload), payment webhooks
├── sdk/          the customer's observe-only Python SDK
├── services/
│   ├── rules/        🔒 the six waste detectors — THE ENGINE (tenant-blind)
│   ├── pricing/      🔒 rate table + coster — money math (rates machine-verified)
│   ├── connectors/   provider pulls, scheduler, daily digest
│   ├── dashboard/    owner-lens widgets
│   ├── payments/     plans, subscriptions, dunning, currency
│   └── alerts/ statements/ report/ copilot/ flywheel/ lifecycle/ ingest/ mail/ collector/
├── persistence/  SQLAlchemy models, repo (sessions + the tenancy chokepoint), Alembic migrations
└── obs/          structlog · Sentry (FR-22-scrubbed) · rate limits
```

### The one hard boundary
The **audit engine — `services/rules` + `services/pricing` — is tenant-blind.**
It runs on rows and never learns about users, workspaces, or the network.
Identity, tenancy, and billing live only at the web/persistence edge. This is
enforced in CI by the import-guard test `T-NFR-01`. When you add a feature,
tenancy code goes at the edge; the engine keeps taking plain data in and
returning plain findings out.

Two more invariants worth knowing on day one:
- **No prompt/completion text is ever persisted** (FR-22) — records store
  counts, ids, hashes, and metadata only.
- **Money math is gated** — any change under `pricing/` or a rules estimator
  ships golden-file updates in the same commit, and `scripts/pricing_verify.py`
  must exit 0 (a wrong rate fails CI).

---

## 6. How work ships: vertical slices

Every change ships **end-to-end or not at all** — the backend change **+** its
UI surface **+** the click-path that reaches it **+** a test that walks it **+**
honest empty/error states, in one slice. A backend with no reachable UI does
not merge. One slice = one branch = one PR.

```
branch off main  →  build the slice  →  open a PR
   →  CI: authorship · ruff · mypy · pytest+coverage · pricing-verify · docs
   →  adversarial gate review  →  squash-merge (green only; main is protected)
   →  auto-promote: deploy → STAGING → smoke → PRODUCTION
```

Staging is the gate: **nothing reaches production that staging didn't prove.**
The app-critical smoke checks (healthz, landing, auth, scheduler) are fatal;
auxiliary surfaces that differ per environment are reported but non-fatal.

### Commit + authorship rules
- Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`, …), one concern each.
- **No AI attribution anywhere** — not in commit trailers, PR bodies, or
  titles. Every commit is authored by the repository owner. Enforced by
  `scripts/check_authorship.py` (a required CI gate).

---

## 7. Common tasks

| Task | Command |
|---|---|
| Run the app (reload) | `uv run uvicorn tokenops_cost_auditor.main:app --reload` |
| Full local stack | `docker compose up -d --build` |
| New migration | `uv run alembic revision -m "NNN_description"` then edit + `alembic upgrade head` |
| Tests (fast) | `uv run pytest -q -m "not perf"` |
| One test file | `uv run pytest -q tests/test_dashboard.py` |
| Lint + format check | `uv run ruff check . && uv run ruff format --check .` |
| Auto-format | `uv run ruff format .` |
| Types | `uv run mypy` |
| Money-math gate | `uv run python scripts/pricing_verify.py` |
| Build the docs site | `uv run mkdocs build --strict` |
| Regenerate the self-audit page | `uv run python scripts/render_self_audit.py` |

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| App won't boot on a fresh `.env` | A blank optional key parsed as `""`. This is handled in `config.py`; if you added a key, ensure blank ⇒ default. |
| `mypy`/`ruff` differ from CI | You ran system Python. Always prefix `uv run`. |
| Postgres connection refused | `docker compose up -d postgres`, then re-run migrations. |
| `alembic upgrade head` fails | Check `DATABASE_URL` in `.env` points at your running Postgres. |
| Payments/mail/OAuth "missing" | Env-gated surfaces stay off until their keys are set — expected locally. |

More: architecture & methods → [`docs/internal/PLATFORM.md`](internal/PLATFORM.md);
requirements & scope → [`docs/01-REQUIREMENTS.md`](01-REQUIREMENTS.md); ops &
deploy → [`docs/06-OPS-RUNBOOK.md`](06-OPS-RUNBOOK.md); current state →
[`STATUS.md`](../STATUS.md).
