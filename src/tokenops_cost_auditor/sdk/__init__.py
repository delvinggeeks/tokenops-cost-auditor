"""TokenOps Cost Auditor SDK (S-1, R-SDK-PLATFORM) — one call, usage flows.

    import tokenops_cost_auditor.sdk as toca
    toca.init()   # reads TOKENOPS_COST_AUDITOR_DSN from the environment

That is the whole setup. After init(), every OpenAI and Anthropic call your
process makes is auto-instrumented: token counts, model, timing and status
are batched and shipped to your account, where they run through the full
six-detector audit. Prompt and completion TEXT are never read, never
serialized, never sent (FR-22 by construction — see sdk/extract.py). The
SDK is OBSERVE-ONLY: it never sits in your request path and never alters,
slows, or breaks a call (X-01 — see sdk/instrument.py). No DSN set = the
SDK is inert, exactly like Sentry.

Also usable explicitly, without the auto-patch:

    toca.record({"provider": "openai", "model": "gpt-5.4", "ts": "...",
                 "prompt_tokens": 3084, "completion_tokens": 47})
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import structlog

from tokenops_cost_auditor.sdk.batcher import Batcher
from tokenops_cost_auditor.sdk.instrument import install_anthropic, install_openai

log = structlog.get_logger("tokenops_cost_auditor.sdk")

DSN_ENV = "TOKENOPS_COST_AUDITOR_DSN"

_batcher: Batcher | None = None
_tag: str = ""


def _parse_dsn(dsn: str) -> tuple[str, str] | None:
    """https://ik_<key>@<host> -> (host_base_url, key). None if malformed.

    Every field access is inside the guard (cold-review f.1): .port raises
    ValueError on a non-numeric port, so a typo'd DSN must return None here,
    never escape as an exception out of init() into the customer's process."""
    try:
        u = urlparse(dsn)
        if not u.username or not u.hostname or u.scheme not in ("http", "https"):
            return None
        # IPv6 hostnames need their brackets back for a valid URL (f.2)
        host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
        port = f":{u.port}" if u.port else ""
    except ValueError:
        return None
    return f"{u.scheme}://{host}{port}", u.username


def init(
    dsn: str | None = None,
    *,
    environment: str | None = None,
    tag: str | None = None,
    flush_interval: float = 5.0,
    batch_size: int = 500,
    max_queue: int = 10_000,
) -> bool:
    """Start the SDK. Returns True if armed, False if no/invalid DSN (inert).

    `environment`/`tag` label your records (folded into the one `tag` field
    the counts-only contract allows — no free-text dimension is invented)."""
    global _batcher, _tag
    dsn = dsn or os.environ.get(DSN_ENV, "")
    if not dsn:
        log.info("sdk.inert", reason=f"no {DSN_ENV}")
        return False
    parsed = _parse_dsn(dsn)
    if parsed is None:
        log.warning("sdk.inert", reason="malformed DSN")
        return False
    host, key = parsed
    # cold-review f.3: a second init() must replace, not stack — else the old
    # daemon thread leaks AND both batchers ship every instrumented call,
    # double-counting usage. Close the previous one first.
    if _batcher is not None:
        _batcher.close()
    _tag = (tag or environment or "")[:120]
    _batcher = Batcher(
        host, key, flush_interval=flush_interval, batch_size=batch_size, max_queue=max_queue
    )
    patched = [
        name
        for name, ok in (
            ("openai", install_openai(record)),
            ("anthropic", install_anthropic(record)),
        )
        if ok
    ]
    log.info("sdk.armed", host=host, instrumented=patched)
    return True


def record(rec: dict[str, Any]) -> None:
    """Enqueue one usage record (counts only). No-op if the SDK is inert.
    The configured tag is attached when the record carries none."""
    if _batcher is None:
        return
    if _tag and "tag" not in rec:
        rec = {**rec, "tag": _tag}
    _batcher.record(rec)


def flush() -> None:
    """Ship everything queued now (best-effort)."""
    if _batcher is not None:
        _batcher.flush()


def close() -> None:
    """Flush and stop. Called automatically at process exit."""
    global _batcher
    if _batcher is not None:
        _batcher.close()
        _batcher = None


def _reset_for_tests() -> None:
    global _batcher, _tag
    _batcher = None
    _tag = ""
