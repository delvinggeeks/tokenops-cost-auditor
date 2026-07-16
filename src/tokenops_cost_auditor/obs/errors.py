"""Error-tracking hook, Sentry-compatible and env-gated (NFR-06).

sentry-sdk is intentionally NOT a project dependency; if SENTRY_DSN is set and the
package is importable, it is initialized — otherwise the hook degrades to structured
error logs only.
"""

import structlog

_log = structlog.get_logger("tokenops_cost_auditor.errors")
_sentry_enabled = False


def init_errors(sentry_dsn: str, app_env: str) -> None:
    global _sentry_enabled
    if not sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=sentry_dsn, environment=app_env)
        _sentry_enabled = True
    except ImportError:
        _log.warning("sentry_dsn_set_but_sdk_missing")


def capture_exception(exc: BaseException) -> None:
    """Called on every unhandled application error (wired in main.py)."""
    if _sentry_enabled:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    _log.error("unhandled_error", exc_info=exc)
