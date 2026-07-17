"""Rate limiting (NFR-03, NFR-12). Keyed per authenticated user when a session
exists, per client IP otherwise; 429 responses carry Retry-After
(headers_enabled). Endpoints attach limits via @limiter.limit(...)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def user_or_ip_key(request: Request) -> str:
    """NFR-12: authenticated user id wins; anonymous traffic falls back to IP."""
    user_email = getattr(request.state, "user_email", None)
    if user_email:
        return f"user:{user_email}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_or_ip_key, headers_enabled=True)
