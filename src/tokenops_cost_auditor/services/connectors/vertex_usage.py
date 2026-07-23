"""Google Vertex AI usage adapter (WP-CLOUD-T2 C-C) — Cloud Monitoring.

Vertex AI publishes token counts as a Cloud Monitoring metric (verified
against Google Cloud docs + the Elastic/Splunk integration references,
2026-07-23):

  aiplatform.googleapis.com/publisher/online_serving/token_count
    metric.label "type" = input | output
    resource.label "model_user_id" = the model (e.g. "gemini-2.5-pro")

Read via the Cloud Monitoring v3 timeSeries.list API with a service
account holding ONLY roles/monitoring.viewer on the project — read-only by
Google IAM, not by our promise. Auth is the standard service-account flow:
a JWT signed RS256 with the SA private key is exchanged at the SA's
token_uri for a short-lived access token (stdlib urllib for the HTTP;
`cryptography`, already a project dependency via Fernet, for the RS256
signature — no new dependency).

Credential: the downloaded service-account JSON key, stored whole on the
existing Fernet path. HONESTY BOUND: this metric splits input/output only,
not cached tokens, so cached_tokens is 0 by construction and the cache
detector is "not observable on Vertex" (R-Q1) — the same honest treatment
as Azure. Counts only leave this module (FR-22); the private key's
plaintext lifetime is one signing pass and it is never logged (T-KEY-03).
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

BASE_URL = "https://monitoring.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/monitoring.read"
METRIC_TYPE = "aiplatform.googleapis.com/publisher/online_serving/token_count"
_REQUIRED_FIELDS = ("client_email", "private_key", "token_uri", "project_id")


class SupportsHttp(Protocol):
    """The httpx.Client slice used here — GET (metrics) + POST (token)."""

    def get(self, url: str, *, params: Any, headers: Any) -> Any: ...

    def post(self, url: str, *, data: Any) -> Any: ...


def parse_credential(blob: str) -> dict[str, str]:
    """The service-account JSON -> field dict; refuses a partial/wrong file."""
    try:
        cred = json.loads(blob)
    except (ValueError, TypeError) as exc:
        raise ConnectorAuthError("stored Google credential is not valid JSON") from exc
    if not isinstance(cred, dict) or any(not cred.get(k) for k in _REQUIRED_FIELDS):
        raise ConnectorAuthError(
            "stored Google credential is missing a field — paste the whole service-account key JSON"
        )
    return {k: str(cred[k]) for k in _REQUIRED_FIELDS}


def normalize_model_id(model_id: str) -> str:
    """Vertex model_user_id -> the stable id our pricing rows key on.

    Strips a publishers/.../models/ path and a trailing -NNN version snapshot
    ("gemini-1.5-flash-002" -> "gemini-1.5-flash")."""
    mid = model_id.rsplit("/", 1)[-1]
    return re.sub(r"-\d{3}$", "", mid)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_jwt(cred: dict[str, str], now: datetime) -> str:
    """RS256 service-account assertion for the token exchange."""
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    iat = int(now.timestamp())
    claims = _b64url(
        json.dumps(
            {
                "iss": cred["client_email"],
                "scope": SCOPE,
                "aud": cred["token_uri"],
                "iat": iat,
                "exp": iat + 3600,
            }
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode()
    key = serialization.load_pem_private_key(cred["private_key"].encode(), password=None)
    if not isinstance(key, RSAPrivateKey):  # a Google SA key is always RSA
        raise ConnectorAuthError("stored Google credential's private key is not RSA")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{_b64url(signature)}"


def _access_token(http: SupportsHttp, cred: dict[str, str], now: datetime) -> str:
    resp = http.post(
        cred["token_uri"],
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": _signed_jwt(cred, now),
        },
    )
    if resp.status_code in (400, 401, 403):
        # bad key / disabled SA / wrong project — the credential is refused
        raise ConnectorAuthError("provider rejected the stored credential", status=resp.status_code)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ConnectorAuthError("provider returned no token for the stored credential")
    return str(token)


def _point_day(point: dict[str, Any]) -> date:
    end = (point.get("interval") or {}).get("endTime") or ""
    return datetime.fromisoformat(str(end).replace("Z", "+00:00")).date()


def _point_value(point: dict[str, Any]) -> int:
    val = point.get("value") or {}
    raw = val.get("int64Value", val.get("doubleValue", 0))
    try:
        return int(float(raw))
    except TypeError, ValueError:
        return 0


def parse_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """timeSeries.list response -> (day, model) buckets, counts only.

    cached_tokens is 0 by construction (this metric has no cache split — see
    the module docstring)."""
    acc: dict[tuple[date, str], dict[str, Any]] = {}
    for series in payload.get("timeSeries", []):
        kind = str((series.get("metric") or {}).get("labels", {}).get("type", "")).lower()
        field = {"input": "prompt_tokens", "output": "completion_tokens"}.get(kind)
        if field is None:
            continue
        model_raw = (series.get("resource") or {}).get("labels", {}).get("model_user_id") or (
            series.get("metric") or {}
        ).get("labels", {}).get("model_user_id", "unknown")
        model = normalize_model_id(str(model_raw))
        for point in series.get("points", []):
            tokens = _point_value(point)
            if not tokens:
                continue
            day = _point_day(point)
            bucket = acc.setdefault(
                (day, model),
                {
                    "day": day,
                    "model": model,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,  # not exposed by this metric (docstring)
                },
            )
            bucket[field] = int(bucket[field]) + tokens
    return [acc[k] for k in sorted(acc, key=lambda k: (k[0].isoformat(), k[1]))]


def _fetch(
    http: SupportsHttp, credential_blob: str, start_day: date, end_day: date
) -> tuple[list[dict[str, Any]], int]:
    cred = parse_credential(credential_blob)
    now = datetime.now(UTC)
    token = _access_token(http, cred, now)
    del credential_blob  # narrow the private key's plaintext lifetime
    start = datetime.combine(start_day, time.min, UTC)
    end = datetime.combine(end_day + timedelta(days=1), time.min, UTC)
    params = {
        "filter": f'metric.type = "{METRIC_TYPE}"',
        "interval.startTime": start.isoformat().replace("+00:00", "Z"),
        "interval.endTime": end.isoformat().replace("+00:00", "Z"),
        "aggregation.alignmentPeriod": "86400s",
        "aggregation.perSeriesAligner": "ALIGN_SUM",
    }
    url = f"{BASE_URL}/v3/projects/{urllib.parse.quote(cred['project_id'])}/timeSeries"
    resp = http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code in (401, 403):
        raise ConnectorAuthError("provider rejected the stored credential", status=resp.status_code)
    resp.raise_for_status()
    return parse_series(resp.json()), 1


def fetch_usage(
    api_key: str,
    start_day: date,
    end_day: date,
    client: SupportsHttp | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Pull [start_day, end_day] inclusive. Returns (buckets, pages).

    `api_key` carries the decrypted service-account JSON — the same registry
    slot every adapter uses, the SA key file inside."""
    if client is not None:
        return _fetch(client, api_key, start_day, end_day)
    with httpx.Client(timeout=30.0) as http:
        return _fetch(http, api_key, start_day, end_day)
