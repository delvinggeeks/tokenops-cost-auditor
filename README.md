# TokenOps Cost Auditor

Audit LLM usage for waste and turn it into a dollar-ranked report with fixes.
Customers connect their usage — upload a log, install the SDK, or connect a
provider (OpenAI · Anthropic · Azure OpenAI · AWS Bedrock · Google Vertex) — and
six detectors (oversized model, missing cache, prompt bloat, retry storms,
unbounded `max_tokens`, chatty loops) surface avoidable spend. It is
**observe-only**: never in the customer's request path — no proxy, no
enforcement.

> **Proprietary — © TokenOps Cost Auditor. All rights reserved.** Private
> repository; not licensed for use, copying, or distribution. See [LICENSE](LICENSE).

---

## Quickstart (local development)

Requires [`uv`](https://docs.astral.sh/uv/) (the pinned Python toolchain) and Docker.
New to the codebase? [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) is the full
step-by-step walkthrough (setup, the dev loop, structure, how slices ship).

```bash
git clone <repo-url> && cd tokenops-cost-auditor
uv sync --all-extras                 # install deps (incl. optional extras)
cp .env.example .env                 # blank values fall back to safe defaults
uv run alembic upgrade head          # apply DB migrations (uses DATABASE_URL)
uv run uvicorn tokenops_cost_auditor.main:app --reload   # http://localhost:8000
```

Run the full stack (app + Postgres + Caddy) with Docker:

```bash
docker compose up -d --build
```

Everything runs through `uv` — never the system Python:

```bash
uv run pytest -q            # tests
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                 # types
make test | make lint       # shortcuts
```

## Architecture

A FastAPI + htmx app over PostgreSQL. The one hard boundary: the **audit engine
(`services/rules` + `services/pricing`) is tenant-blind** — it runs on rows and
never learns about users or workspaces; identity, tenancy, and billing live only
at the web/persistence edge (enforced by CI test `T-NFR-01`).

```
src/tokenops_cost_auditor/
├── web/          FastAPI routes + htmx templates (dashboard, sources, runs, reports, settings, developer)
├── api/          machine surfaces — /api/v1/ingest (upload), payment webhooks
├── sdk/          the customer's observe-only Python SDK
├── services/
│   ├── rules/        🔒 the six waste detectors (the engine — tenant-blind)
│   ├── pricing/      🔒 rate table + coster (money math; rates machine-verified)
│   ├── connectors/   provider pulls, the scheduler, the daily digest
│   ├── dashboard/    owner-lens widgets (metrics, savings, explorer, activity)
│   ├── payments/     plans, subscriptions, dunning, currency
│   └── alerts/ statements/ report/ copilot/ flywheel/ lifecycle/ ingest/ mail/ collector/
├── persistence/  SQLAlchemy models, repo (sessions + the tenancy chokepoint), Alembic migrations
└── obs/          structlog · Sentry (FR-22-scrubbed) · rate limits
```

The full system map — components, tenancy model, methods, tools, and the docs
index — is [`docs/internal/PLATFORM.md`](docs/internal/PLATFORM.md).

## Project layout

| Path | What |
|---|---|
| `src/` | application code (subsystem hierarchy above) |
| `tests/` | pytest suite (~1:1 test:code ratio) |
| `docs/` | architecture & requirements (`00-PRD` … `13-*`), the traceability matrix, [`DEVELOPMENT.md`](docs/DEVELOPMENT.md) |
| `docs/design/` | design-system source (`wa-design.css`, `icons.svg`), motion specs, mockups, evidence |
| `docs/internal/` | plans, STATUS history, runbooks, the ownership map, launch analysis — internal working docs |
| `docs-site/` | the public documentation site (mkdocs) |
| `deploy/` | Terraform (Hetzner) + one-command provisioning |
| `scripts/` | provisioning, pricing verification, doc generation |
| `.github/workflows/` | CI (lint/type/test/coverage/pricing/docs/authorship) + staging→prod deploy |

## Development workflow

Every change is a **vertical slice** (backend + UI + click-path + test, shipped
end-to-end) that flows through CI + an adversarial gate review before merge, and
deploys via a **staging → production** promotion (staging is the gate; nothing
reaches prod that staging didn't prove). See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Proprietary. All rights reserved — see [LICENSE](LICENSE).
