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

from typing import Any, cast

import structlog

_log = structlog.get_logger("tokenops_cost_auditor.errors")
_sentry_enabled = False

_SCRUBBED_REQUEST_KEYS = ("data", "cookies", "headers", "query_string", "env")


def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """before_send: counts-and-stacks only (FR-22). Never customer content.

    Defense in depth alongside include_local_variables=False (cold-review
    f.1: frame locals ship by default and send_default_pii does NOT govern
    them) — even if a future SDK default drifts, frame vars, extra and
    contexts are stripped here before anything leaves the box."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in _SCRUBBED_REQUEST_KEYS:
            request.pop(key, None)
    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values") or []:
            if not isinstance(value, dict):
                continue
            frames = (value.get("stacktrace") or {}).get("frames") or []
            for frame in frames:
                if isinstance(frame, dict):
                    frame.pop("vars", None)
    # breadcrumbs replay log lines, which may carry emails/labels — drop whole
    event.pop("breadcrumbs", None)
    event.pop("user", None)
    event.pop("extra", None)
    event.pop("contexts", None)
    return event


def init_errors(sentry_dsn: str, app_env: str, release: str = "") -> None:
    global _sentry_enabled
    # unconditional reset FIRST (cold-review f.2): a re-init WITHOUT a DSN
    # must disarm reporting — the zero-egress promise cannot depend on
    # process history.
    _sentry_enabled = False
    if not sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=app_env,
            release=release or None,
            send_default_pii=False,
            # frame locals ship by DEFAULT and are NOT governed by
            # send_default_pii — a connector parse error would carry the raw
            # provider response verbatim (cold-review f.1, FR-22 hard rule)
            include_local_variables=False,
            # the SDK types events as its own TypedDict; the scrubber is
            # deliberately plain-dict so tests need no sdk installed
            before_send=cast("Any", _scrub),
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
