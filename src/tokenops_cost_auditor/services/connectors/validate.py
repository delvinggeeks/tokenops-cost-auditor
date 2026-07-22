"""Live key validation for the Connect wizard (PLAN-V15 V-D9 / R-MAGIC-CONNECT).

We ask the provider for one day of usage with the pasted key and report, in
plain words, one of three verdicts:

  ok          the key can read usage — we are connected, read-only
  no_scope    the key is valid but cannot read usage reports
  unreachable we could not reach the provider just now

R-WIZ-DEGRADE (founder): `unreachable` is NOT a failure. The key is saved
and validated again on the first pull, because a customer's first minute
must never hang on a provider's status page. The timeout here is short for
the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from tokenops_cost_auditor.services.connectors import anthropic_usage, openai_usage
from tokenops_cost_auditor.services.connectors.base import SupportsGet
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

log = structlog.get_logger("tokenops_cost_auditor.connectors")

OK = "ok"
BAD_KEY = "bad_key"
NO_SCOPE = "no_scope"
UNREACHABLE = "unreachable"

# Short on purpose: the wizard must never feel hung (R-WIZ-DEGRADE).
TIMEOUT_S = 6.0


@dataclass(frozen=True)
class Verdict:
    status: str
    headline: str
    detail: str
    can_save: bool  # ok and unreachable both save; no_scope does not


VERDICTS = {
    OK: Verdict(
        status=OK,
        headline="Connected — we can see your usage.",
        detail=(
            "Read-only: we can read your usage reports and nothing else. "
            "We can never see your prompts or make calls on your account."
        ),
        can_save=True,
    ),
    BAD_KEY: Verdict(
        status=BAD_KEY,
        headline="We couldn't authenticate that key.",
        detail=(
            "The provider didn't recognise it — it may be mistyped, revoked, "
            "or from a different organization. Create a fresh Admin key and "
            "paste it again."
        ),
        can_save=False,
    ),
    NO_SCOPE: Verdict(
        status=NO_SCOPE,
        headline="This key can't read usage reports.",
        detail=(
            "The key authenticates, but it isn't an organization Admin key, so "
            "the provider won't let it read usage and cost. Create an Admin key "
            "(only an org owner/admin can) and paste it again."
        ),
        can_save=False,
    ),
    UNREACHABLE: Verdict(
        status=UNREACHABLE,
        headline="We couldn't reach your provider just now.",
        detail=(
            "That's almost always them, not you. We've saved your key and "
            "we'll check it again on the first pull — nothing else for you "
            "to do. You can also try again now."
        ),
        can_save=True,
    ),
}


def validate_key(provider: str, api_key: str, client: SupportsGet | None = None) -> Verdict:
    """One day of usage is enough to prove the key can read reports."""
    end = datetime.now(UTC).date()
    start = end - timedelta(days=1)
    fetch = {
        "openai": openai_usage.fetch_usage,
        "anthropic": anthropic_usage.fetch_usage,
    }.get(provider)
    if fetch is None:
        raise ValueError(f"unknown provider: {provider}")

    own_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        fetch(api_key, start, end, http)
        return VERDICTS[OK]
    except ConnectorAuthError as exc:
        # The provider actively refused the key — a real answer, so we do NOT
        # save it. Tell the truth about WHICH refusal: 401 = the key itself is
        # bad/revoked; 403 = the key is valid but lacks admin permission.
        return VERDICTS[BAD_KEY] if exc.status == 401 else VERDICTS[NO_SCOPE]
    except Exception as exc:
        log.info("connect.validate_unreachable", provider=provider, error=str(exc)[:120])
        return VERDICTS[UNREACHABLE]
    finally:
        if own_client and isinstance(http, httpx.Client):
            http.close()
