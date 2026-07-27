"""IP -> ISO country code resolution (Issue #68).

Order: a configurable trusted proxy header (default `CF-IPCountry`, set by
Cloudflare's free tier) first — one header read, no lookup; else a GeoIP
lookup on the real client IP (X-Forwarded-For's first hop, else the socket
peer) against a DB-IP Lite Country `.mmdb` (free, CC-BY, no license key) IF
`settings.geoip_db_path` is configured and exists; else `None`. The caller
(services/payments/plans) maps `"IN"` to INR and everything else — including
a miss — to USD, so a lookup failure is always a safe, silent USD default.
Never raises.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import maxminddb
import structlog

if TYPE_CHECKING:
    from fastapi import Request

    from tokenops_cost_auditor.config import Settings

log = structlog.get_logger("tokenops_cost_auditor.geo")

# Cloudflare's documented sentinel for "no country could be determined"
# (Tor exit nodes, non-geolocatable ranges) — treat it as a miss, not a code.
_CF_UNKNOWN = "XX"


@lru_cache(maxsize=8)
def _reader(db_path: str) -> maxminddb.Reader | None:
    try:
        return maxminddb.open_database(db_path)
    except Exception:
        log.warning("geo.db_open_failed", path=db_path)
        return None


def _client_ip(request: Request) -> str | None:
    """The real client IP: X-Forwarded-For's first hop (we run behind a
    proxy that forwards it) ahead of the socket peer, which would otherwise
    be the proxy itself."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client is not None:
        return request.client.host
    return None


def _country_from_db(ip: str, db_path: str) -> str | None:
    reader = _reader(db_path)
    if reader is None:
        return None
    try:
        result = reader.get(ip)
    except Exception:
        return None  # malformed IP or lookup failure — a miss, never a crash
    if not isinstance(result, dict):
        return None
    country = result.get("country")
    if not isinstance(country, dict):
        return None
    code = country.get("iso_code")
    return code.upper() if isinstance(code, str) and code else None


def country_for_request(request: Request, settings: Settings) -> str | None:
    """The viewer's ISO country code, or `None` on any miss. Never throws —
    every lookup failure (bad header, no DB, malformed IP, closed db file)
    falls through to `None` and the caller defaults to USD."""
    header_name = settings.geo_country_header or "CF-IPCountry"
    header_val = request.headers.get(header_name)
    if header_val:
        code = header_val.strip().upper()
        if code and code != _CF_UNKNOWN:
            return code
    db_path = settings.geoip_db_path
    if db_path and Path(db_path).exists():
        ip = _client_ip(request)
        if ip:
            return _country_from_db(ip, db_path)
    return None
