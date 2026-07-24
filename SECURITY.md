# Security Policy

TokenOps Cost Auditor is a private, proprietary system. Security is a first-class
constraint of the design:

- The audit **engine never sees prompt or completion text** — records store
  counts, ids, and metadata only (FR-22). There is no column for message text.
- The engine is **observe-only** — never in the customer's request path (no
  proxy, no enforcement).
- Connector credentials are **encrypted at rest** (Fernet); revocation deletes
  the ciphertext, not just a flag.
- Error reports are **scrubbed** before leaving the process (request bodies,
  headers, cookies, env, and user data are stripped; only the stack + route +
  release survive).
- Production is key-only SSH, firewalled (22/80/443), TLS via Caddy, with
  pre-deploy backups and automatic rollback on a failed smoke.

## Reporting a vulnerability

Do **not** open a public issue or PR for a security report. Contact the
maintainer privately at **delving.geeks@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof-of-concept if possible),
- any affected versions/commits.

You'll get an acknowledgement, and fixes ride the normal
gate → staging → production pipeline (expedited for severe issues).

## Scope

Reports about this codebase and its deployed surfaces are in scope. Do not test
against production in a way that degrades service for others; request a staging
target if you need to validate a fix.
