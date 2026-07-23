"""Azure OpenAI usage adapter (WP-CLOUD-T2 C-A) — Azure Monitor metrics.

Azure OpenAI has no OpenAI-style /organization/usage endpoint. The billable
counts live as Azure Monitor platform metrics on the Cognitive Services
resource (verified against Microsoft's monitoring reference, 2026-07-23):

  ProcessedPromptTokens   input tokens   (Sum, split by ModelName)
  GeneratedTokens         output tokens  (Sum, split by ModelName)
  AzureOpenAIRequests     call counts    (Sum, split by ModelName)

Auth is an Entra ID service principal holding ONLY the Monitoring Reader
role on ONE resource — read-only by Azure's own RBAC, not by our promise.
The stored credential is a JSON object of four fields (tenant_id,
client_id, client_secret, resource_id), encrypted whole on the existing
Fernet path; this module receives the decrypted JSON string where other
adapters receive a bare key.

HONESTY BOUND: Azure exposes no cached-token COUNT for standard
deployments (only a PTU-only cache match RATE), so cached_tokens is 0 by
construction here and the cache detector is labeled "not observable on
Azure" in coverage — never run against a fake zero (R-Q1 law).

Counts only leave this module (FR-22). The client secret's plaintext
lifetime is one token exchange; it is never logged (T-KEY-03 law).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

import httpx

from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

LOGIN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
BASE_URL = "https://management.azure.com"
METRICS_API_VERSION = "2023-10-01"  # GA metrics REST API version
METRIC_NAMES = "ProcessedPromptTokens,GeneratedTokens,AzureOpenAIRequests"

_REQUIRED_FIELDS = ("tenant_id", "client_id", "client_secret", "resource_id")


class SupportsHttp(Protocol):
    """The slice of httpx.Client this adapter uses — lets tests inject a fake.
    Azure needs POST (token exchange) on top of the shared GET contract."""

    def get(self, url: str, *, params: Any, headers: Any) -> Any: ...

    def post(self, url: str, *, data: Any) -> Any: ...


def parse_credential(blob: str) -> dict[str, str]:
    """The decrypted credential JSON -> field dict; refuses partial grants."""
    try:
        cred = json.loads(blob)
    except (ValueError, TypeError) as exc:
        raise ConnectorAuthError("stored Azure credential is malformed") from exc
    if not isinstance(cred, dict) or any(not cred.get(k) for k in _REQUIRED_FIELDS):
        raise ConnectorAuthError("stored Azure credential is missing a field")
    return {k: str(cred[k]) for k in _REQUIRED_FIELDS}


def _token(http: SupportsHttp, cred: dict[str, str]) -> str:
    """Client-credentials exchange for a management-plane bearer token."""
    resp = http.post(
        LOGIN_URL.format(tenant=cred["tenant_id"]),
        data={
            "grant_type": "client_credentials",
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "scope": f"{BASE_URL}/.default",
        },
    )
    if resp.status_code in (400, 401, 403):
        # Azure returns 400 for bad client secrets/ids on this endpoint;
        # every one of these means "the stored grant is not accepted".
        raise ConnectorAuthError("provider rejected the stored credential", status=resp.status_code)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ConnectorAuthError("provider returned no token for the stored credential")
    return str(token)


def parse_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One metrics response -> flat bucket dicts keyed (day, model).

    Each metric arrives as its own timeseries per ModelName; buckets merge
    the three metrics on the (day, model) key. cached_tokens is 0 by
    construction (see module docstring) — the coverage label carries the
    honesty, not a fake count."""
    acc: dict[tuple[date, str], dict[str, Any]] = {}
    for metric in payload.get("value", []):
        name = str(((metric.get("name") or {}).get("value")) or "")
        field = {
            "ProcessedPromptTokens": "prompt_tokens",
            "GeneratedTokens": "completion_tokens",
            "AzureOpenAIRequests": "calls",
        }.get(name)
        if field is None:
            continue
        for series in metric.get("timeseries", []):
            model = "unknown"
            for md in series.get("metadatavalues", []):
                if str(((md.get("name") or {}).get("value")) or "").lower() == "modelname":
                    model = str(md.get("value") or "unknown")
            for point in series.get("data", []):
                total = point.get("total")
                if not total:  # absent or 0.0 — nothing billed in this grain
                    continue
                day = datetime.fromisoformat(str(point["timeStamp"]).replace("Z", "+00:00")).date()
                bucket = acc.setdefault(
                    (day, model),
                    {
                        "day": day,
                        "model": model,
                        "calls": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "cached_tokens": 0,  # not exposed by Azure (module docstring)
                    },
                )
                # round, never truncate: Azure's Sum aggregation returns
                # floats (12345.9999…); int() would undercount every bucket
                # (cold-review f.1 — rule 4 reaches connectors too).
                bucket[field] = round(bucket[field] + float(total))
    return [acc[k] for k in sorted(acc, key=lambda k: (k[0].isoformat(), k[1]))]


def _fetch(
    http: SupportsHttp, credential_blob: str, start_day: date, end_day: date
) -> tuple[list[dict[str, Any]], int]:
    cred = parse_credential(credential_blob)
    token = _token(http, cred)
    del credential_blob  # narrow the secret's plaintext lifetime
    span_start = datetime.combine(start_day, time.min, UTC)
    span_end = datetime.combine(end_day + timedelta(days=1), time.min, UTC)
    resp = http.get(
        f"{BASE_URL}{cred['resource_id']}/providers/microsoft.insights/metrics",
        params={
            "api-version": METRICS_API_VERSION,
            "metricnames": METRIC_NAMES,
            "aggregation": "Total",
            "interval": "P1D",
            "timespan": f"{span_start.isoformat()}/{span_end.isoformat()}",
            "$filter": "ModelName eq '*'",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code in (401, 403):
        raise ConnectorAuthError("provider rejected the stored credential", status=resp.status_code)
    resp.raise_for_status()
    return parse_metrics(resp.json()), 1


def fetch_usage(
    api_key: str,
    start_day: date,
    end_day: date,
    client: SupportsHttp | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Pull [start_day, end_day] inclusive. Returns (buckets, pages).

    `api_key` carries the decrypted four-field credential JSON — same slot
    the registry hands every adapter, different shape inside (the wizard
    packs it; parse_credential unpacks and refuses partial grants)."""
    if client is not None:
        return _fetch(client, api_key, start_day, end_day)
    with httpx.Client(timeout=30.0) as http:
        return _fetch(http, api_key, start_day, end_day)
