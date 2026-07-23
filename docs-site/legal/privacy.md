# Privacy Policy

Effective 2026-07-17

<!-- MP-9 single-sourcing: mirrors the binding web page at /legal/privacy
     (templates/legal/privacy.html); sync test asserts the FR-23 string and
     section structure match. The web page is the authoritative copy. -->

Your uploaded logs are
"analyzed then deleted; nothing retained beyond 7 days; your logs and prompts are never used to train any model."

Anonymized usage counts and fix outcomes — never your content — power cross-customer benchmarks every customer benefits from. You can exclude your account any time in Settings.

**What we collect.** Your email address (for sign-in links and report
delivery), the log file you upload, payment references from our payment
providers, and standard server logs (request IDs, IP addresses for security
and rate limiting).

**What happens to your logs.** Uploads are stored encrypted at rest and
processed by a deterministic rules engine on our own server — no AI model and
no third party ever reads them. Raw uploads are automatically purged 7 days
after your report is generated; every purge is written to an append-only audit
log. What remains: token counts, per-day/per-model aggregates, your findings,
and your report.

**What we never store.** Prompt or completion text is never written to our
database — the engine keeps token counts and metadata only, and this is
enforced by automated tests.

**Sharing.** No selling, no sharing with third parties, no training on your
data. Payment processing happens at Razorpay/Stripe; they see payment details,
never your logs.

**Your controls.** Ask us to purge your uploads at any time before the
automatic purge; ask for deletion of your account and reports whenever you
like.

**Transport & storage.** TLS in transit; encrypted disk at rest; secrets
managed outside the codebase.
