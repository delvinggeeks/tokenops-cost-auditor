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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from tokenops_cost_auditor.services.connectors import (
    anthropic_usage,
    azure_usage,
    bedrock_usage,
    openai_usage,
    vertex_usage,
)
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


# Azure refusals name Azure's own objects (ux gate note 8: error copy must
# say what went wrong and how to fix it — "Admin key" words would mislead).
AZURE_OVERRIDES = {
    BAD_KEY: Verdict(
        status=BAD_KEY,
        headline="Azure couldn't authenticate those values.",
        detail=(
            "One of the four values is wrong, or the client secret has "
            "expired. Check the Directory ID, Application ID and Resource ID "
            "against the portal — or create a fresh client secret and paste "
            "its Value (not its ID)."
        ),
        can_save=False,
    ),
    NO_SCOPE: Verdict(
        status=NO_SCOPE,
        headline="This principal can't read metrics on that resource.",
        detail=(
            "The credentials authenticate, but the app is missing the "
            "Monitoring Reader role on the resource you pasted. On the "
            "resource: Access control (IAM) → Add role assignment → "
            "Monitoring Reader → select your app, then try again."
        ),
        can_save=False,
    ),
}


# Bedrock refusals name AWS's own objects (same law as the Azure overrides).
BEDROCK_OVERRIDES = {
    BAD_KEY: Verdict(
        status=BAD_KEY,
        headline="AWS couldn't authenticate that key pair.",
        detail=(
            "The Access key ID or Secret access key is wrong, deactivated, "
            "or the region doesn't match. Check all three against IAM — or "
            "create a fresh access key and paste both values again."
        ),
        can_save=False,
    ),
    NO_SCOPE: Verdict(
        status=NO_SCOPE,
        headline="This key can't read CloudWatch metrics.",
        detail=(
            "The key authenticates, but its IAM user is missing CloudWatch "
            "read access. Attach the CloudWatchReadOnlyAccess policy (or an "
            "inline policy allowing cloudwatch:GetMetricData and "
            "cloudwatch:ListMetrics), then try again."
        ),
        can_save=False,
    ),
}


# Vertex refusals name Google's own objects (same law as Azure/Bedrock).
VERTEX_OVERRIDES = {
    BAD_KEY: Verdict(
        status=BAD_KEY,
        headline="Google couldn't authenticate that key.",
        detail=(
            "The service-account key was rejected — it may be the wrong file, "
            "disabled, or from a different project. Create a fresh JSON key for "
            "the service account and paste the whole file again."
        ),
        can_save=False,
    ),
    NO_SCOPE: Verdict(
        status=NO_SCOPE,
        headline="This service account can't read metrics.",
        detail=(
            "The key authenticates, but the service account is missing the "
            "Monitoring Viewer role on the project. Grant roles/monitoring.viewer "
            "to the service account, then try again."
        ),
        can_save=False,
    ),
}


def validate_key(provider: str, api_key: str, client: SupportsGet | None = None) -> Verdict:
    """One day of usage is enough to prove the key can read reports."""
    end = datetime.now(UTC).date()
    start = end - timedelta(days=1)
    # One calling shape, provider-specific client protocols (Azure also
    # POSTs its token exchange) — Callable[...] mirrors pull.py's registry.
    fetchers: dict[str, Callable[..., tuple[list[dict[str, Any]], int]]] = {
        "openai": openai_usage.fetch_usage,
        "anthropic": anthropic_usage.fetch_usage,
        "azure-openai": azure_usage.fetch_usage,
        "bedrock": bedrock_usage.fetch_usage,
        "vertex-ai": vertex_usage.fetch_usage,
    }
    fetch = fetchers.get(provider)
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
        # Azure's token endpoint answers 400 for bad ids/secrets — same
        # meaning as 401 here: the credential itself is not accepted. Status
        # 0 (typed errors with no HTTP code: malformed blob, token-less
        # response) is ALSO a credential fault — the role-gap diagnosis
        # would be a wrong fix for it (cold-review f.2).
        status = BAD_KEY if exc.status in (0, 400, 401) else NO_SCOPE
        if provider == "azure-openai":
            return AZURE_OVERRIDES[status]
        if provider == "bedrock":
            return BEDROCK_OVERRIDES[status]
        if provider == "vertex-ai":
            return VERTEX_OVERRIDES[status]
        return VERDICTS[status]
    except Exception as exc:
        log.info("connect.validate_unreachable", provider=provider, error=str(exc)[:120])
        return VERDICTS[UNREACHABLE]
    finally:
        if own_client and isinstance(http, httpx.Client):
            http.close()
