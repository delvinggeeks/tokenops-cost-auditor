"""FastAPI app factory, middleware, routers (docs/03-LLD.md §1)."""

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from tokenops_cost_auditor.config import Settings, get_settings
from tokenops_cost_auditor.obs import errors as obs_errors
from tokenops_cost_auditor.obs.logging import configure_logging, request_id_middleware
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.repo import make_engine

log = structlog.get_logger("tokenops_cost_auditor")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.app_env)
    obs_errors.init_errors(settings.sentry_dsn, settings.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.engine.dispose()

    app = FastAPI(title="TokenOps Cost Auditor", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.limiter = limiter

    async def rate_limited(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RateLimitExceeded)
        return _rate_limit_exceeded_handler(request, exc)

    app.add_exception_handler(RateLimitExceeded, rate_limited)
    app.middleware("http")(request_id_middleware)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        obs_errors.capture_exception(exc)  # NFR-06; internals to logs only (LLD §8)
        return JSONResponse(status_code=500, content={"error": "internal error"})

    @app.get("/healthz")
    async def healthz(request: Request) -> JSONResponse:  # NFR-05; contract in LLD §5
        db_ok = True
        try:
            with request.app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        disk_free_mb = shutil.disk_usage(".").free // (1024 * 1024)
        ok = db_ok and disk_free_mb > 500
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ok": ok, "db": db_ok, "disk_free_mb": disk_free_mb},
        )

    return app


app = create_app()
