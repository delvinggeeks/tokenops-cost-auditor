"""Server-side geo resolution (Issue #68) — IP to country, zero cost, no key.

Replaces the browser-side timezone-cookie JS and the Accept-Language sniff
that used to stand in for region detection (both were guesses; this is
server truth on the FIRST request). See `resolver.country_for_request`.
"""
