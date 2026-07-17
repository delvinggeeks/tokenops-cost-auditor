# Security

The threat model is simple to state: your uploaded logs are the crown jewels,
and the biggest risks are exfiltration, retention beyond promise, and privileged
misuse. Every mechanism below exists against one of those.
<!-- src: docs/02 §6; runbook §5 -->

## Authentication

Magic links are signed tokens with a 15-minute expiry, single-use by
construction: consuming one records the login instant, and any token issued at
or before that instant is dead — there is no consumed-token table to fail
open. Sessions are signed cookies flagged `HttpOnly`, `Secure`,
`SameSite=Lax`. The magic-link request endpoint answers identically whether or
not an account exists (no enumeration signal) and is rate-limited.
<!-- src: FR-17; web/auth.py; NFR-03 -->

## Admin isolation

The admin panel requires an `X-Admin-Token` compared in constant time; absent
or wrong tokens get 404 — the panel does not exist for unauthenticated eyes.
Every admin action is written to the append-only audit log with the acting
IP. <!-- src: FR-19/20; routes_admin.py -->

## Upload handling

Uploads are size-capped, content-sniffed, stored on a non-executable path
outside the web root, and parsed by code that drops text fields at the door.
The parser never echoes file content in error messages.
<!-- src: runbook §5; docs/03 §8 -->

## Payments

Webhooks are verified with stdlib HMAC (no payment SDK in the attack surface),
bound by a 5-minute timestamp tolerance, and deduplicated in an append-only
event table — replays cannot double-grant. Credits are consumed with an atomic
compare-and-claim, so two concurrent uploads cannot spend one payment.
<!-- src: FR-27; G5 remediation: atomic claim_credit -->

## Transport, storage, secrets

TLS everywhere via Caddy auto-TLS; encrypted disk at rest; secrets only in the
environment file (never the repo); Postgres reachable only on the compose
network. Structured logs carry request IDs, never log content.
<!-- src: NFR-02/05 -->

## Enforced data policy

The 7-day purge is a tested scheduled job; the no-text-persisted rule is a
tested property of the schema; the audit log is INSERT-only in code and loses
UPDATE/DELETE grants at the database role level in deploy.
<!-- src: FR-21/22; T-LIF tests -->

## Self-enforced product boundaries

The out-of-scope list is part of the requirements spec: no live proxy or
gateway in your request path (X-01), no policy/budget enforcement acting on
your account (X-02), no multi-org RBAC/SSO (X-03), no LLM-generated narrative
in reports (X-04), no SPA frontend (X-05). A gate agent checks every milestone
diff against these. We publish them because a tool that *could* sit in your
request path is a different risk conversation than one that structurally
cannot. <!-- src: docs/01 §G -->
