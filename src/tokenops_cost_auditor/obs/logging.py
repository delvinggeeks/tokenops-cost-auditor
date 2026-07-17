"""Structured JSON logging with request IDs (NFR-05)."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


def configure_logging(app_env: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),  # NFR-11: UTC
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=False,
    )


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
    request.state.request_id = request_id  # NFR-14 envelope reads this
    structlog.contextvars.bind_contextvars(request_id=request_id)
    log = structlog.get_logger("tokenops_cost_auditor.request")
    start = time.monotonic()
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    # request_id passed explicitly as well so log-capture tests see it without
    # relying on contextvar merge order (T-OBS-01).
    log.info(
        "request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.monotonic() - start) * 1000, 2),
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
