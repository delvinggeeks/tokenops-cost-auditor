"""OpenAI Usage API client (T2; PLAN-V15 WP-1).

GET /v1/organization/usage/completions with bucket_width=1d and
group_by=model, admin/org key auth. Field mapping (documented per docs/12
Stage-1 contract):

  num_model_requests            -> calls
  input_tokens                  -> prompt_tokens (includes cached)
  input_cached_tokens           -> cached_tokens
  output_tokens                 -> completion_tokens
  bucket start_time (epoch s)   -> day (UTC date)

Prompt/completion content does not exist in this API; only counts are read
(FR-22 at the door). Pagination via `next_page`. Network access lives in
this package only — the engine import guard (T-NFR-01) is untouched.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from tokenops_cost_auditor.services.connectors.base import SupportsGet

BASE_URL = "https://api.openai.com/v1/organization/usage/completions"
PAGE_LIMIT = 31  # days per page at 1d buckets


class ConnectorAuthError(Exception):
    """Provider refused the key. `status` carries the HTTP code so callers can
    tell a bad/revoked key (401) from a real-but-unpermitted key (403) —
    reporting a typo'd key as a permission problem is a false diagnosis
    (readiness audit 2026-07-22). Message stays user-safe (no key echo)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def parse_page(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One API page -> flat bucket dicts (day/model/counts)."""
    out: list[dict[str, Any]] = []
    for bucket in payload.get("data", []):
        day = datetime.fromtimestamp(int(bucket["start_time"]), tz=UTC).date()
        for result in bucket.get("results", []):
            out.append(
                {
                    "day": day,
                    "model": str(result.get("model") or "unknown"),
                    "calls": int(result.get("num_model_requests") or 0),
                    "prompt_tokens": int(result.get("input_tokens") or 0),
                    "completion_tokens": int(result.get("output_tokens") or 0),
                    "cached_tokens": int(result.get("input_cached_tokens") or 0),
                }
            )
    return out


def _fetch(
    http: SupportsGet, api_key: str, start_day: date, end_day: date
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "start_time": int(datetime.combine(start_day, datetime.min.time(), UTC).timestamp()),
        "end_time": int(
            datetime.combine(end_day + timedelta(days=1), datetime.min.time(), UTC).timestamp()
        ),
        "bucket_width": "1d",
        "group_by": ["model"],
        "limit": PAGE_LIMIT,
    }
    buckets: list[dict[str, Any]] = []
    pages = 0
    while True:
        resp = http.get(BASE_URL, params=params, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code in (401, 403):
            raise ConnectorAuthError(
                "provider rejected the stored key", status=resp.status_code
            )
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
    """Pull [start_day, end_day] inclusive. Returns (buckets, pages)."""
    if client is not None:
        return _fetch(client, api_key, start_day, end_day)
    with httpx.Client(timeout=30.0) as http:
        return _fetch(http, api_key, start_day, end_day)
