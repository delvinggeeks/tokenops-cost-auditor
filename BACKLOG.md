# BACKLOG.md — scope parking lot

Per PRD §10 change control: scope additions during the 14-day build are rejected by
default and parked here. Promotion requires a founder-written amendment in
docs/00-PRD.md.

## Deliberately OUT — trigger register (R-API, 2026-07-17)

Recorded triggers, not build items. When a trigger fires, notify the founder;
promotion still requires a PRD amendment.

- **API keys / programmatic access** — trigger: first customer request.
  Treat the request itself as a BUYING SIGNAL and notify the founder immediately.
- **Queue/workers (replacing BackgroundTasks + NFR-13 cap)** — trigger: the
  MAX_CONCURRENT_AUDITS cap regularly saturated (queue depth alerts in digest).
- **Orgs/SSO** (X-03 stands) — trigger: first team customer.
- **SOC2 track** — trigger: enterprise procurement blocker.

## Parked ideas

- **Aggregate-mode audit** (2026-07-17, source: docs/09b §5.5): accept provider
  Usage-API/console exports (time-bucketed aggregates, no per-request rows) with a
  reduced detector set (D2 missing-cache via cached-token fields + model-mix
  analysis). Widens funnel to customers with zero request logging. Out of frozen v1
  scope; requires founder PRD amendment to promote.
