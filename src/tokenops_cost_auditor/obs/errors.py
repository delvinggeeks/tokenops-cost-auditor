"""Error-tracking hook, Sentry-compatible and env-gated (NFR-06; activated
for our own production by WP-DEVOPS-OBS, founder 2026-07-23).

sentry-sdk ships as the OPTIONAL `obs` extra (installed in our image, never
a hard dependency): customer in-VPC deployments keep the zero-egress
posture of R-DEPLOYMENT-CONTRACT by simply not setting SENTRY_DSN — without
a DSN the SDK is never initialized and the hook degrades to structured
error logs only, exactly as before.

FR-22 travels here too: `_scrub` strips request payloads, headers, cookies,
query strings and breadcrumbs from every event before it leaves the box —
an error report carries the stack and the release tag, never customer
content or identifiers beyond what the stack itself names. `release` is
the deployed git tag (RELEASE_TAG stamped by provision.sh), so every event
maps to the exact deploy that produced it.
"""

from typing import Any

import structlog

_log = structlog.get_logger("tokenops_cost_auditor.errors")
_sentry_enabled = False

_SCRUBBED_REQUEST_KEYS = ("data", "cookies", "headers", "query_string", "env")


def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """before_send: counts-and-stacks only (FR-22). Never customer content."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in _SCRUBBED_REQUEST_KEYS:
            request.pop(key, None)
    # breadcrumbs replay log lines, which may carry emails/labels — drop whole
    event.pop("breadcrumbs", None)
    event.pop("user", None)
    return event


def init_errors(sentry_dsn: str, app_env: str, release: str = "") -> None:
    global _sentry_enabled
    if not sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=app_env,
            release=release or None,
            send_default_pii=False,
            before_send=_scrub,
        )
        _sentry_enabled = True
    except ImportError:
        _log.warning("sentry_dsn_set_but_sdk_missing")


def capture_exception(exc: BaseException) -> None:
    """Called on every unhandled application error (wired in main.py)."""
    if _sentry_enabled:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    _log.error("unhandled_error", exc_info=exc)
