# TokenOps Cost Auditor — application image.
# Python 3.14 choice recorded in PLAN.md §0.2 (wheel verification 2026-07-17).
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# weasyprint runtime libs (Pango/HarfBuzz/Fontconfig) — see docs/03-LLD.md render_pdf
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
        libfontconfig1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first for build caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY src ./src
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# Non-root runtime user; uploads/reports stored outside web root (HLD §6)
RUN useradd --create-home --uid 1000 tokenops_cost_auditor \
    && mkdir -p /data/uploads /data/reports \
    && chown -R tokenops_cost_auditor:tokenops_cost_auditor /data /app

USER tokenops_cost_auditor
ENV PATH="/app/.venv/bin:$PATH" \
    UPLOAD_DIR=/data/uploads \
    REPORT_DIR=/data/reports

EXPOSE 8000

# runbook §1: uvicorn, single worker. With --workers >1 uvicorn's multiprocess
# supervisor pings workers (5s pipe timeout, supervisors/multiprocess.py) and
# REPLACES any that miss it — CPU-saturated audit threads on small VPS cores
# miss the ping and the kill orphans in-flight audits (D13 re-validation,
# 2026-07-19, "Child process died" ×2 with zero OOM). Single worker = no
# supervisor; audit concurrency is governed by MAX_CONCURRENT_AUDITS (NFR-13).
CMD ["uvicorn", "tokenops_cost_auditor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
