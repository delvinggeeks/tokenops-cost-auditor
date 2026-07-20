"""Anthropic Admin Usage API client (T2; PLAN-V15 WP-1).

GET /v1/organizations/usage_report/messages with bucket_width=1d and
group_by[]=model, admin key auth (x-api-key). Field mapping (docs/12
Stage-1 contract):

  uncached_input_tokens + cache_read_input_tokens
    + cache-creation tokens          -> prompt_tokens
  cache_read_input_tokens            -> cached_tokens
  output_tokens                      -> completion_tokens
  bucket starting_at (ISO)           -> day (UTC date)
  (calls: the API does not expose a per-bucket request count on all
   versions; num_requests is read when present, else 0 — the aggregate
   detectors treat calls==0 buckets as uneligible for per-call averages.)

Counts only (FR-22 at the door). Pagination via `next_page`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from tokenops_cost_auditor.services.connectors.base import SupportsGet
from tokenops_cost_auditor.services.connectors.openai_usage import ConnectorAuthError

BASE_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _cache_creation_tokens(result: dict[str, Any]) -> int:
    """Cache-creation tokens appear either flat (cache_creation_input_tokens)
    or nested by TTL ({"cache_creation": {"ephemeral_5m_input_tokens": ...}});
    sum whatever is present."""
    flat = result.get("cache_creation_input_tokens")
    if flat is not None:
        return int(flat)
    nested = result.get("cache_creation") or {}
    return sum(int(v or 0) for v in nested.values())


def parse_page(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in payload.get("data", []):
        day = datetime.fromisoformat(str(bucket["starting_at"]).replace("Z", "+00:00")).date()
        for result in bucket.get("results", []):
            uncached = int(result.get("uncached_input_tokens") or 0)
            cached = int(result.get("cache_read_input_tokens") or 0)
            creation = _cache_creation_tokens(result)
            out.append(
                {
                    "day": day,
                    "model": str(result.get("model") or "unknown"),
                    "calls": int(result.get("num_requests") or 0),
                    "prompt_tokens": uncached + cached + creation,
                    "completion_tokens": int(result.get("output_tokens") or 0),
                    "cached_tokens": cached,
                }
            )
    return out


def _fetch(
    http: SupportsGet, api_key: str, start_day: date, end_day: date
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "starting_at": f"{start_day.isoformat()}T00:00:00Z",
        "ending_at": f"{end_day.isoformat()}T23:59:59Z",
        "bucket_width": "1d",
        "group_by[]": "model",
    }
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
    buckets: list[dict[str, Any]] = []
    pages = 0
    while True:
        resp = http.get(BASE_URL, params=params, headers=headers)
        if resp.status_code in (401, 403):
            raise ConnectorAuthError("provider rejected the stored key (revoked or scoped?)")
        resp.raise_for_status()
        payload = resp.json()
        buckets.extend(parse_page(payload))
        pages += 1
        next_page = payload.get("next_page")
        if not next_page or not payload.get("has_more"):
            break
        params["page"] = next_page
    return buckets, pages


def fetch_usage(
    api_key: str,
    start_day: date,
    end_day: date,
    client: SupportsGet | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if client is not None:
        return _fetch(client, api_key, start_day, end_day)
    with httpx.Client(timeout=30.0) as http:
        return _fetch(http, api_key, start_day, end_day)
