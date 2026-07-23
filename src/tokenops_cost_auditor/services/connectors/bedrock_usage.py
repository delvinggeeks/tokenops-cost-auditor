"""AWS Bedrock usage adapter (WP-CLOUD-T2 C-B) — CloudWatch metrics.

Bedrock publishes its billable counts as CloudWatch metrics in the
AWS/Bedrock namespace (verified against AWS docs, 2026-07-23):

  Invocations             call counts        (Sum, by ModelId)
  InputTokenCount         uncached input     (Sum, by ModelId)
  OutputTokenCount        output tokens      (Sum, by ModelId)
  CacheReadInputTokens    cache-read input   (Sum, by ModelId)
  CacheWriteInputTokens   cache-write input  (Sum, by ModelId)

Token composition mirrors anthropic_usage.parse_page exactly — Bedrock's
runtime usage fields share the Anthropic semantics (inputTokens EXCLUDES
cache fields): prompt_tokens = Input + CacheRead + CacheWrite;
cached_tokens = CacheRead. Unlike Azure, Bedrock EXPOSES cache counts, so
the cache detector runs honestly on this provider.

Credential: three fields (access_key_id, secret_access_key, region) packed
to canonical JSON by the wizard, encrypted whole on the existing Fernet
path. The IAM grant is read-only (cloudwatch:GetMetricData + ListMetrics)
— enforced by AWS IAM, not by our promise. Requests are SigV4-signed with
stdlib hmac/hashlib; the decrypted secret is held in memory only for the
pull's duration and is never logged (T-KEY-03 law; cold-review f.1 made
this claim honest — it signs every page of the pull, not one pass).

ModelId normalization: region-routing prefixes (us./eu./apac./global.),
ARN tails, and trailing -vN:M version suffixes are stripped, so
"us.anthropic.claude-sonnet-5-v1:0" prices as "anthropic.claude-sonnet-5".
Models without a verified rate land in unpriced_models (FR-28: listed,
never guessed). Counts only leave this module (FR-22).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

import httpx

from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

BASE_URL = "https://monitoring.{region}.amazonaws.com"
SERVICE = "monitoring"
NAMESPACE = "AWS/Bedrock"
TARGET_PREFIX = "GraniteServiceVersion20100801"
METRIC_FIELDS = {
    "Invocations": "calls",
    "InputTokenCount": "input",
    "OutputTokenCount": "completion_tokens",
    "CacheReadInputTokens": "cache_read",
    "CacheWriteInputTokens": "cache_write",
}
_REQUIRED_FIELDS = ("access_key_id", "secret_access_key", "region")
_REGION_RE = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")


def is_valid_region(region: str) -> bool:
    """Public pre-check for callers (routes) — the private regex stays
    private (cold-review f.2: reaching past the underscore turns a future
    rename into a 500 where a 400 belongs)."""
    return bool(_REGION_RE.match(region))


# credential faults vs permission gaps — AWS answers both as HTTP 4xx with a
# typed body; the distinction drives which fix the wizard suggests.
_BAD_CREDENTIAL_TYPES = ("InvalidClientTokenId", "SignatureDoesNotMatch", "UnrecognizedClient")


class SupportsSignedPost(Protocol):
    """The slice of httpx.Client this adapter uses — lets tests inject a
    fake. Both CloudWatch calls are JSON-protocol POSTs."""

    def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> Any: ...


def parse_credential(blob: str) -> dict[str, str]:
    """The decrypted credential JSON -> field dict; refuses partial grants."""
    try:
        cred = json.loads(blob)
    except (ValueError, TypeError) as exc:
        raise ConnectorAuthError("stored AWS credential is malformed") from exc
    if not isinstance(cred, dict) or any(not cred.get(k) for k in _REQUIRED_FIELDS):
        raise ConnectorAuthError("stored AWS credential is missing a field")
    if not _REGION_RE.match(str(cred["region"])):
        raise ConnectorAuthError("stored AWS credential has an invalid region")
    return {k: str(cred[k]) for k in _REQUIRED_FIELDS}


def normalize_model_id(model_id: str) -> str:
    """Bedrock ModelId/ARN -> the stable id our pricing rows key on."""
    mid = model_id.rsplit("/", 1)[-1]  # ARN or inference-profile tail
    for prefix in ("us.", "eu.", "apac.", "global.", "jp.", "au."):
        if mid.startswith(prefix):
            mid = mid[len(prefix) :]
            break
    return re.sub(r"-v\d+(:\d+)?$", "", mid)


def _sign(cred: dict[str, str], body: bytes, target: str, now: datetime) -> dict[str, str]:
    """SigV4 request headers for one CloudWatch JSON-protocol POST."""
    host = f"{SERVICE}.{cred['region']}.amazonaws.com"
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day_stamp = now.strftime("%Y%m%d")
    content_type = "application/x-amz-json-1.0"
    payload_hash = hashlib.sha256(body).hexdigest()
    signed_headers = "content-type;host;x-amz-date;x-amz-target"
    canonical = "\n".join(
        [
            "POST",
            "/",
            "",
            f"content-type:{content_type}",
            f"host:{host}",
            f"x-amz-date:{amz_date}",
            f"x-amz-target:{target}",
            "",
            signed_headers,
            payload_hash,
        ]
    )
    scope = f"{day_stamp}/{cred['region']}/{SERVICE}/aws4_request"
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical.encode()).hexdigest(),
        ]
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hmac(f"AWS4{cred['secret_access_key']}".encode(), day_stamp)
    k_region = _hmac(k_date, cred["region"])
    k_service = _hmac(k_region, SERVICE)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "X-Amz-Date": amz_date,
        "X-Amz-Target": target,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={cred['access_key_id']}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


def _call(
    http: SupportsSignedPost, cred: dict[str, str], action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = _sign(cred, body, f"{TARGET_PREFIX}.{action}", datetime.now(UTC))
    resp = http.post(BASE_URL.format(region=cred["region"]), content=body, headers=headers)
    if resp.status_code in (400, 403):
        try:
            err_type = str(resp.json().get("__type", ""))
        except Exception:
            err_type = ""
        if any(t in err_type for t in _BAD_CREDENTIAL_TYPES):
            # the key itself is not accepted — a credential fault (401-class)
            raise ConnectorAuthError("provider rejected the stored credential", status=401)
        if resp.status_code == 403 or "AccessDenied" in err_type:
            raise ConnectorAuthError("provider rejected the stored credential", status=403)
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


def _list_model_ids(http: SupportsSignedPost, cred: dict[str, str]) -> tuple[list[str], int]:
    """Discover which ModelIds have Bedrock token metrics; returns (ids, pages)."""
    ids: set[str] = set()
    pages = 0
    token: str | None = None
    while True:
        payload: dict[str, Any] = {"Namespace": NAMESPACE, "MetricName": "InputTokenCount"}
        if token:
            payload["NextToken"] = token
        data = _call(http, cred, "ListMetrics", payload)
        pages += 1
        for metric in data.get("Metrics", []):
            for dim in metric.get("Dimensions", []):
                if dim.get("Name") == "ModelId" and dim.get("Value"):
                    ids.add(str(dim["Value"]))
        token = data.get("NextToken")
        if not token:
            return sorted(ids), pages


def _ts_to_date(value: Any) -> date:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC).date()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def parse_metric_data(
    payload: dict[str, Any], id_map: dict[str, tuple[str, str]]
) -> dict[tuple[date, str], dict[str, int]]:
    """One GetMetricData response -> {(day, model): {field: count}} — raw
    fields; bucket composition happens in _fetch so partially-missing
    metrics stay explicit."""
    acc: dict[tuple[date, str], dict[str, int]] = {}
    for series in payload.get("MetricDataResults", []):
        mapped = id_map.get(str(series.get("Id", "")))
        if mapped is None:
            continue
        model, field = mapped
        for ts, value in zip(series.get("Timestamps", []), series.get("Values", []), strict=False):
            if not value:
                continue
            day = _ts_to_date(ts)
            slot = acc.setdefault((day, model), {})
            # round, never truncate (C-A cold-review f.1 — rule 4 reaches
            # connectors): CloudWatch Sums arrive as floats.
            slot[field] = slot.get(field, 0) + round(float(value))
    return acc


def _fetch(
    http: SupportsSignedPost, credential_blob: str, start_day: date, end_day: date
) -> tuple[list[dict[str, Any]], int]:
    cred = parse_credential(credential_blob)
    del credential_blob
    model_ids, pages = _list_model_ids(http, cred)
    if not model_ids:
        return [], pages
    start = datetime.combine(start_day, time.min, UTC)
    end = datetime.combine(end_day + timedelta(days=1), time.min, UTC)
    queries: list[dict[str, Any]] = []
    id_map: dict[str, tuple[str, str]] = {}
    for m_idx, model_id in enumerate(model_ids):
        for f_idx, (metric, field) in enumerate(METRIC_FIELDS.items()):
            qid = f"q{m_idx}_{f_idx}"
            id_map[qid] = (normalize_model_id(model_id), field)
            queries.append(
                {
                    "Id": qid,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": NAMESPACE,
                            "MetricName": metric,
                            "Dimensions": [{"Name": "ModelId", "Value": model_id}],
                        },
                        "Period": 86400,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )
    acc: dict[tuple[date, str], dict[str, int]] = {}
    # GetMetricData accepts <=500 queries per call; 5 metrics x N models
    # stays under that until ~100 models, but chunk anyway — no silent caps.
    for i in range(0, len(queries), 500):
        chunk = queries[i : i + 500]
        token = None
        while True:
            payload = {
                "StartTime": int(start.timestamp()),
                "EndTime": int(end.timestamp()),
                "MetricDataQueries": chunk,
            }
            if token:
                payload["NextToken"] = token
            data = _call(http, cred, "GetMetricData", payload)
            pages += 1
            for key, fields in parse_metric_data(data, id_map).items():
                slot = acc.setdefault(key, {})
                for field, count in fields.items():
                    slot[field] = slot.get(field, 0) + count
            token = data.get("NextToken")
            if not token:
                break
    buckets: list[dict[str, Any]] = []
    for (day, model), fields in sorted(acc.items(), key=lambda k: (k[0][0].isoformat(), k[0][1])):
        cache_read = fields.get("cache_read", 0)
        cache_write = fields.get("cache_write", 0)
        buckets.append(
            {
                "day": day,
                "model": model,
                "calls": fields.get("calls", 0),
                # anthropic_usage composition, verbatim: total input =
                # uncached + cache reads + cache writes.
                "prompt_tokens": fields.get("input", 0) + cache_read + cache_write,
                "completion_tokens": fields.get("completion_tokens", 0),
                "cached_tokens": cache_read,
            }
        )
    return buckets, pages


def fetch_usage(
    api_key: str,
    start_day: date,
    end_day: date,
    client: SupportsSignedPost | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Pull [start_day, end_day] inclusive. Returns (buckets, pages).

    `api_key` carries the decrypted three-field credential JSON — the same
    registry slot every adapter uses, a different shape inside."""
    if client is not None:
        return _fetch(client, api_key, start_day, end_day)
    with httpx.Client(timeout=30.0) as http:
        return _fetch(http, api_key, start_day, end_day)
