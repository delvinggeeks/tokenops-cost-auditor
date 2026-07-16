# Claude Code Kickoff — TokenOps Cost Auditor (v1.3, fresh start + agent harness)

Starting state: EMPTY repository containing only this docs/ folder.
Setup step BEFORE pasting the prompt: copy docs/claude-agents/*.md into
.claude/agents/ in the repo root (mkdir -p .claude/agents && cp
docs/claude-agents/*.md .claude/agents/).

```
You are building TokenOps Cost Auditor, a production micro-SaaS, in an
EMPTY repository. No templates, no prior code, no boilerplates, no
third-party skill packs. You scaffold everything from scratch per the
spec kit in docs/:
  00-PRD, 01-REQUIREMENTS, 02-HLD, 03-LLD, 04-TRACEABILITY,
  05-TEST-PLAN, 06-OPS-RUNBOOK, 07-ROADMAP, 09-MARKET-RESEARCH,
  10-AGENT-HARNESS.

READ ALL SPEC DOCS COMPLETELY BEFORE ANY CODE. docs/10-AGENT-HARNESS.md
governs how you and the gate agents in .claude/agents/ operate.

SCAFFOLD FROM SCRATCH (D1):
- uv-managed Python 3.13 project, src layout exactly per docs/03-LLD.md
  (verify all wheels resolve; if pandas/pyarrow/weasyprint/psycopg all
  install cleanly on 3.14 you may use 3.14 — record the choice in
  PLAN.md)
- pyproject.toml: fastapi, uvicorn, sqlalchemy, alembic, psycopg,
  pydantic-settings, jinja2, weasyprint, pandas, pyarrow, itsdangerous,
  structlog, slowapi, pytest, pytest-cov, hypothesis, ruff, mypy
- Dockerfile + docker-compose.yml (app, postgres:17, caddy) per
  docs/06-OPS-RUNBOOK.md; .env.example covering every variable in
  docs/03-LLD.md section 7
- GitHub Actions CI per docs/05-TEST-PLAN.md section 4
- STATUS.md (shared memory file per TE-4)
- CLAUDE.md at repo root containing ONLY:
  (1) scope freeze — X-01..X-05 forbidden; new ideas -> BACKLOG.md
  (2) services/rules and services/pricing: zero network/LLM imports
      (import-guard test T-NFR-01)
  (3) no prompt/completion text persisted anywhere (FR-22)
  (4) money-math changes require golden-file update + spreadsheet diff
      in the commit message
  (5) docs/04-TRACEABILITY.md updated in the same commit as any
      implemented requirement
  (6) conventional commits; milestone Dn ends all-green before Dn+1
  (7) TOKEN ECONOMY: rules TE-1..TE-10 and kill switches K-1..K-4 from
      docs/10-AGENT-HARNESS.md section 2 and 5, copied verbatim
- Do NOT install any third-party skills, agent packs, or boilerplates.

GATE PROTOCOL (docs/10-AGENT-HARNESS.md sections 3-4):
At the END of each Dn milestone, invoke the scheduled gate agents from
.claude/agents/ IN ORDER, passing each: the milestone git diff,
STATUS.md, and only its charter-named docs. A FAIL verdict stops the
milestone: fix in main thread, re-run that gate on the new diff only.
Never invoke gates per-prompt or per-file. Update STATUS.md (one
paragraph) after gates pass, then /clear context per TE-9 before Dn+1.

TOKEN DISCIPLINE (your own conduct):
- grep/offset reads, never whole-repo exploration
- two failed fix attempts on the same test = STOP and ask (K-2)
- note accumulated context at each milestone; >200K = /clear + reload
  PLAN.md + STATUS.md + current Dn section only (K-3, TE-9)

FIRST TASK (then STOP for my approval):
Write PLAN.md mapping docs/07-ROADMAP.md D1-D7 into concrete work
packages: files to create, tests per package (IDs from docs/05), gate
schedule per milestone (from docs/10 section 3), and any spec
ambiguities as numbered questions. No application code until I approve
PLAN.md.
```
