# Engineering

This section publishes how the auditor is built: requirements, architecture,
test strategy, security posture, performance evidence.

Why publish internals? Because for this product, **transparency is the
product**. You are trusting our arithmetic with a purchasing decision and our
infrastructure with your logs. Every dollar figure in a report traces to a
documented formula, a versioned rate card, and a pinned test; every privacy
claim traces to an enforced mechanism. These pages let you check that chain
yourself instead of taking our word for it.

- [Requirements](requirements.md) — what the product commits to, grouped
  readably.
- [Architecture](architecture.md) — the monolith, its boundaries, and the
  decision records behind them.
- [Stack](stack.md) — technology choices and their reasons.
- [Traceability](traceability.md) — the requirement→code→test discipline, with
  the live matrix.
- [Testing](testing.md) — golden fixtures, false-positive guards, property
  tests.
- [Integration](integration.md) — deploy topology and CI pipeline.
- [Security](security.md) — threat model and enforced boundaries.
- [Performance](performance.md) — targets and measured results.
