"""Auto-instrumentation (S-1) — the Sentry-style "init and done" magic.

`init()` monkey-patches the OpenAI and Anthropic client libraries IF they
are importable. Each patch wraps the create() method so that the REAL call
runs first and its result is returned UNMODIFIED — the recording is a
best-effort side effect in a try/except, so a bug in our SDK can never
break, slow, or alter a customer's LLM call (X-01 observe-only, proven by
the wrapper's structure and its tests).

Patching is idempotent (a sentinel attribute guards double-wrap) and
version-tolerant (missing attributes are skipped, never raised).
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

import structlog

from tokenops_cost_auditor.sdk.extract import extract_anthropic, extract_openai

log = structlog.get_logger("tokenops_cost_auditor.sdk")

RecordFn = Callable[[dict[str, Any]], None]
ExtractFn = Callable[..., dict[str, Any] | None]

_MARK = "_tokenops_cost_auditor_wrapped"


def _wrap(owner: Any, method_name: str, extractor: ExtractFn, record: RecordFn) -> bool:
    """Wrap owner.method_name so it records usage after the real call."""
    original = getattr(owner, method_name, None)
    if original is None or getattr(original, _MARK, False):
        return False

    @functools.wraps(original)  # keep name/signature so introspection works (f.4)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        response = original(*args, **kwargs)  # the REAL call — never altered
        try:
            rec = extractor(response, time.monotonic() - t0)
            if rec is not None:
                record(rec)
        except Exception as exc:
            log.debug("sdk.instrument_error", error=str(exc)[:120])
        return response

    setattr(wrapper, _MARK, True)
    setattr(owner, method_name, wrapper)
    return True


def install_openai(record: RecordFn) -> bool:
    """Patch openai chat.completions (sync + async no-op today). Returns
    True if the library was present and patched."""
    try:
        from openai.resources.chat import completions  # type: ignore[import-not-found]
    except Exception:
        return False
    return _wrap(completions.Completions, "create", extract_openai, record)


def install_anthropic(record: RecordFn) -> bool:
    try:
        from anthropic.resources import messages  # type: ignore[import-not-found]
    except Exception:
        return False
    return _wrap(messages.Messages, "create", extract_anthropic, record)
