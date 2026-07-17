# Data Processing Addendum (one-pager)

Effective 2026-07-17 · incorporated into the Terms for business customers

<!-- MP-9 single-sourcing: mirrors the binding web page at /legal/dpa
     (templates/legal/dpa.html); sync test asserts section structure matches.
     The web page is the authoritative copy. -->

**Roles.** You are the controller of the uploaded logs; we are the processor,
acting only on your documented instruction: produce the audit report.

**Scope of data.** LLM API usage logs, which may contain prompt text.
Processing is limited to parsing, token accounting, deterministic waste
analysis, and report rendering.

**Retention.** Raw uploads: purged 7 days after report generation (automated,
audit-logged). Derived aggregates and reports: retained for your access;
deleted on request. No prompt/completion text persists beyond the raw file
lifetime.

**Subprocessors.** Hosting provider (server + storage) and payment providers
(Razorpay/Stripe — payment data only). No analytics or AI subprocessors touch
your logs.

**Security.** TLS in transit, encrypted disk at rest, least-privilege access,
append-only audit log of privileged actions, automated purge.

**Incidents.** We notify you without undue delay after becoming aware of a
personal-data breach affecting your uploads.

**Assistance & deletion.** We support access/deletion requests and delete or
return data at contract end. On-request purge is self-serve.
