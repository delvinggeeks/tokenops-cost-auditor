"""FastAPI app factory, middleware, routers (docs/03-LLD.md §1).

FR-25: the product API mounts under /api/v1. NFR-14: every /api/* error renders
the single envelope {error: {code, message, request_id}}. /healthz stays at the
root (infrastructure endpoint, not part of the product API; docs/03 §5).
"""

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from tokenops_cost_auditor.api.routes_upload import router as audits_router
from tokenops_cost_auditor.api.routes_webhooks import router as webhooks_router
from tokenops_cost_auditor.config import Settings, get_settings
from tokenops_cost_auditor.obs import errors as obs_errors
from tokenops_cost_auditor.obs.logging import configure_logging, request_id_middleware
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.repo import make_engine, make_session_factory
from tokenops_cost_auditor.services.mail.base import LogMailAdapter
from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter
from tokenops_cost_auditor.services.payments.razorpay_link import RazorpayLinkAdapter
from tokenops_cost_auditor.services.payments.stripe_link import StripeLinkAdapter
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.runner import AuditRunner
from tokenops_cost_auditor.web.routes_admin import router as admin_router
from tokenops_cost_auditor.web.routes_alerts import router as alerts_router
from tokenops_cost_auditor.web.routes_auth import router as auth_router
from tokenops_cost_auditor.web.routes_dashboard import router as dashboard_router
from tokenops_cost_auditor.web.routes_pages import router as pages_router
from tokenops_cost_auditor.web.routes_report import router as report_router
from tokenops_cost_auditor.web.routes_sources import router as sources_router

log = structlog.get_logger("tokenops_cost_auditor")

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    402: "payment_required",
    404: "not_found",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}


def error_envelope(request: Request, status: int, message: str) -> JSONResponse:
    """NFR-14: single JSON error envelope for all /api/v1 errors."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": ERROR_CODES.get(status, f"http_{status}"),
                "message": message,
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


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
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.pricing_table = PricingTable.load()
    # FR-20: SMTP adapter is env-gated; log adapter otherwise (dev/test)
    app.state.mail = (
        SmtpMailAdapter(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
            settings.app_base_url,
        )
        if settings.smtp_host
        else LogMailAdapter()
    )
    app.state.razorpay = RazorpayLinkAdapter(
        settings.razorpay_payment_link_url, settings.razorpay_webhook_secret
    )
    app.state.stripe = StripeLinkAdapter(
        settings.stripe_payment_link_url, settings.stripe_webhook_secret
    )
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "web" / "static"),
        name="static",
    )
    app.state.jinja = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "web" / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    app.state.runner = AuditRunner(
        settings=settings,
        table=app.state.pricing_table,
        engine=app.state.engine,
        mail=app.state.mail,
    )
    app.state.limiter = limiter
    app.middleware("http")(request_id_middleware)
    app.include_router(audits_router)  # FR-25: /api/v1 prefix set on the router
    app.include_router(webhooks_router)  # /api/v1/webhooks/* (FR-18/FR-27)
    app.include_router(report_router)  # web report page (FR-15), not under /api
    app.include_router(auth_router)  # magic-link auth (FR-17)
    app.include_router(pages_router)  # landing/upload/legal (FR-23)
    app.include_router(admin_router)  # admin panel (FR-19)
    app.include_router(sources_router)  # T2 connect/revoke (v1.5 WP-1)
    app.include_router(dashboard_router)  # owner dashboard + guide + tour (v1.5 WP-2)
    app.include_router(alerts_router)  # observe-and-alert settings (v1.5 WP-3b)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RateLimitExceeded)
        response = error_envelope(request, 429, f"rate limit exceeded: {exc.detail}")
        # slowapi fills Retry-After / X-RateLimit-* from the view state (NFR-12)
        if hasattr(request.state, "view_rate_limit"):
            request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, HTTPException)
        if request.url.path.startswith("/api/"):
            return error_envelope(request, exc.status_code, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RequestValidationError)
        if request.url.path.startswith("/api/"):
            return error_envelope(request, 422, "request validation failed")
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        obs_errors.capture_exception(exc)  # NFR-06; internals to logs only (LLD §8)
        if request.url.path.startswith("/api/"):
            return error_envelope(request, 500, "internal error")
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
