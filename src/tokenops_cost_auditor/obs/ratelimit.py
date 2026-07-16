"""Rate limiting (NFR-03). Upload and auth endpoints attach limits when they land
(D6/D8); the limiter and 429 handler are wired app-wide from D1."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
