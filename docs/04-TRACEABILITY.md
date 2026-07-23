# Traceability Matrix — TokenOps Cost Auditor v1.0

Req → HLD component → LLD module(s) → Test ID(s) → public docs page. Test
details in 05-TEST-PLAN.md. CI gate: every M-priority FR/NFR row must have ≥1
passing test; matrix checked in review before merge to main. DOC column added
at D-DOCS (DOCS-PLAN §5.4): the docs-site page that covers the requirement
publicly ("—" = internal-only, no public page needed).

| Req    | HLD | LLD module(s)                              | Tests | DOC (docs-site/) |
|--------|-----|--------------------------------------------|-------|------------------|
| FR-01  | C1,C2 | web/upload, api/routes_upload, ingest/*  | T-ING-01..04, T-API-01 | quickstart, api/overview |
| FR-02  | C2  | ingest/normalizer                          | T-ING-05..07 | quickstart |
| FR-03  | C2  | ingest/validator                           | T-ING-08..09 | concepts/how-it-works |
| FR-04  | C2  | cli.py                                     | T-CLI-01 | quickstart |
| FR-05  | C3  | pricing/table, data/prices.yaml            | T-PRC-01..03 | concepts/pricing-data |
| FR-06  | C3  | pricing/coster                             | T-PRC-04..05 | concepts/pricing-data |
| FR-07  | C4  | rules/d1_oversized_model                   | T-RUL-D1-01..03 | concepts/waste-classes/oversized-model |
| FR-08  | C4  | rules/d2_missing_cache                     | T-RUL-D2-01..03 | concepts/waste-classes/missing-cache |
| FR-09  | C4  | rules/d3_prompt_bloat                      | T-RUL-D3-01..02 | concepts/waste-classes/prompt-bloat |
| FR-10  | C4  | rules/d4_retry_storm                       | T-RUL-D4-01..02 | concepts/waste-classes/retry-storms |
| FR-11  | C4  | rules/d5_unbounded_max_tokens              | T-RUL-D5-01..02 | concepts/waste-classes/unbounded-max-tokens |
| FR-12  | C4  | rules/d6_chatty_loop                       | T-RUL-D6-01..03 | concepts/waste-classes/chatty-loops |
| FR-13  | C4  | rules/findings, rules/registry             | T-RUL-00, T-RUL-EV-01 | report/reading-a-report |
| FR-14  | C5  | report/model, render_json, render_pdf      | T-REP-01..04 | report/reading-a-report |
| FR-15  | C5  | report/signer, web/report                  | T-REP-05..06 | api/overview |
| FR-16  | C5  | report (synthetic fixture)                 | T-REP-07 (S) | report/worked-example |
| FR-17  | C1  | web/auth (magic link)                      | T-AUTH-01..04 | api/overview |
| FR-18  | C7  | payments/*, api/routes_webhooks            | T-PAY-01..05 | api/overview |
| FR-19  | C1  | web/admin                                  | T-ADM-01..05 | — |
| FR-20  | C8  | mail/*                                     | T-MAIL-01 (S) | — |
| FR-21  | C6  | lifecycle/purge, lifecycle/auditlog        | T-LIF-01..03 | concepts/data-handling |
| FR-22  | C4,C6 | rules/findings(EvidenceRef), persistence; extended to connector/streamed tiers (founder 2026-07-20, GRAND ORDER v2 — v1.5 connectors must add tier tests) | T-LIF-04, T-RUL-EV-01 | concepts/data-handling |
| FR-23  | C1  | web/templates/landing                      | T-WEB-01 | index, legal/privacy |
| FR-24  | C2  | scripts/exporters/claude_code_export.py    | T-EXP-01..02 | quickstart |
| FR-25  | C1  | main.py router mounting, api/*             | T-API-03 | api/overview |
| FR-26  | C2  | api/routes_upload, persistence (idem keys) | T-API-04..05 | api/overview |
| FR-27  | C7  | api/routes_webhooks, persistence (events)  | T-PAY-06..07 | api/overview |
| FR-28  | C5  | report/model, render_json, render_pdf      | T-REP-08 | concepts/pricing-data |
| FR-29  | Ops | scripts/pricing_refresh.py                 | T-OPS-04 | concepts/pricing-data |
| FR-30  | C5  | report/model (equiv-spend flag), _report_body | T-REP-09 | quickstart |
| FR-31  | v1.5 | DEFERRED BY RULING: R-PIPELINE-UI-SEQ (founder Option A, 2026-07-27) moved the runs/audits list into WP-PIPELINE-UI, FIRST post-launch gated milestone (purged rows metadata-only travels with it); pre-launch carve-out (live theater + row-errors download) shipped v1.5.2 | assigned at WP-PIPELINE-UI | — |
| V15 R-Q1 | C4,C5 | rules/aggregate (d1/d2/d3 aggregate estimators; INACTIVE law), connectors/source_audit (tier+coverage) | T-AGG-01..05, T-SA-01..03, T-REP-03 | engineering/performance (tier note pending WP-7) |
| V15 R-CONNECT | C6 | connectors/{openai,anthropic}_usage, pull (idempotent upsert + stats), schedule (tick), crypto (HKDF/Fernet) | T-CON-01..06, T-SCH-01..03, T-KEY-01..03, T-V15-MIG-01 | — |
| V15 R-Q5/Q6 | C6 | web/routes_sources (plan gating, revoke deletes ciphertext) | tests/test_sources_routes.py | — |
| V15 WP-3b alerts | C6 | services/alerts (observe-only), web/routes_alerts (threshold editor — the single editor, linked from Settings) | T-ALR-01..05, tests/test_alerts.py::TestAlertsPage | — |
| V15 WP-4 statement | C5,C6 | services/statements/build (R-Q9 + R-STMT-MONTH), web/routes_statements | T-STMT-01..03 | — |
| V15 WP-5 settings | C6 | web/routes_settings, services/lifecycle/purge (one purge_one primitive: scheduled/admin/customer) | T-SET-01..03 + purge scoping/idempotence | — |
| R-PRICING-FINAL-2 | C6,C7 | config (list+launch prices, cohort, gates), payments/plans (cohort_used/launch_open/viewer_currency — the code-enforced flip), landing/billing/alerts templates (one currency per view), scripts/daily_digest (cohort-full founder notice) | tests/test_pricing_final.py | — |
| R-DAILY-LOOP | C6,C8 | connectors/daily (digest + 50/80/100 budget stages, audit-identical rate math), schedule.tick, dashboard/metrics yesterday_spend + widget, migration 008 (users.last_daily_digest_at) | tests/test_daily_loop.py | — |
| R-FED-MAJORS | C6 | web/routes_auth FEDERATIONS registry (Google/Microsoft/GitHub, cookie-pinned state, full-pair gating) | tests/test_federation.py | — |
| R-LIVE-PRICING | C3,Ops | pricing/table (overlay merge, append-only), scripts/pricing_sync (fetch LiteLLM feed → gate-validate → auto-write overlay; --cover-from-usage self-heals + re-audits), ofelia (pricing-sync-refresh daily, pricing-cover 3h), scripts/daily_digest (sync FYI + held-swing alert) | tests/test_pricing_sync.py | concepts/pricing-data |
| R-LIVE-AUDIT | C6 | web/routes_sources (_kickoff_first_pull creates queued Audit synchronously, drives queued→processing→done/failed), connectors/source_audit (finalize a pre-created row), templates/_wizard_verdict (land on the live theater) | tests/test_source_audit.py::TestLiveAuditLifecycle | — |
| R-FLYWHEEL L3 (deterministic-now) | C6,C8 | services/forecast (before-the-invoice month-end projection + overspend anomaly, alert-only/X-02, Honesty-Law basis, holds the alert on an unpriced baseline), dashboard/metrics.forecast + _forecast.html widget, connectors/daily (digest heads-up line + subject), config (connect_backfill_days 365, forecast_overspend_pct) | tests/test_forecast.py, tests/test_daily_loop.py::TestForecastAnomalyInDigest | — |
| FR-32 | C5,C6 | services/dashboard/explorer (filter/compose + overlap law + serialize_filters), web/routes_explorer (+saved-view CRUD), templates/app/explore.html, help_registry (explore destination), migration 014 saved_views (C3, R-PROCEED — export HELD on the data-export trigger) | tests/test_explorer.py — T-EXP-F-01..09 map in module docstring + TestBareAudits + TestSavedViews (whitelist sanitization, scoping, replace-on-name, stated limit) | — |
| R-MULTI-SOURCE | C6 | migration 013 (audits.source_id + sources.key_fingerprint, additive), connectors/crypto.credential_fingerprint, connectors/pull (backfill), connectors/source_audit + routes_sources (attribution stamp; fingerprint dedup replaces per-provider block; label suffixing), explorer per-account filter, sources.html View-usage links | tests/test_connect_wizard.py::TestMultiSource, tests/test_connectors.py::TestFingerprintBackfill, tests/test_explorer.py::TestPerSource | — |
| R-F1-SIGNOFF | C1,C5,C6 | promise copy: report/model.DATA_HANDLING, _public_shell footer, legal/{terms,privacy}.html, docs-site mirrors; users.benchmark_sharing + migration 015; routes_settings save_benchmark_pref (audit-logged) + settings.html surface | tests/test_settings.py::TestBenchmarkSharing, updated FR-23 consts in tests/test_{polish,docs_site,auth}.py, tests/test_report_web.py | legal/privacy |
| M-FLY-0 (docs/12 Stage 3) | C6,Ops | services/flywheel/{frame,cohort} (FRAME_COLUMNS allowlist + ENUM_OR_ID law, cohort_pseudonym HKDF, rung thresholds from config), scripts/flywheel_extract.py, scripts/daily_digest (rung line), routes_admin (row), config flywheel_* | tests/test_flywheel.py T-FLY-01..09 (determinism, schema law, pseudonymity, R-F1 exclusion, exact boundaries, founder-surfaces-only, package posture) | — |
| NFR-01 | C4  | rules/* (import guard test)                | T-NFR-01 | concepts/how-it-works, engineering/testing |
| NFR-02 | Ops | Caddyfile, config                          | T-OPS-01 (manual) | engineering/security |
| NFR-03 | C9  | obs/ratelimit                              | T-NFR-03 | api/overview |
| NFR-04 | C2..C4 | runner (perf fixture 1M rows); bound amended to 660s on 4-vCPU class (founder 2026-07-20, D13 VPS measured 624s) | T-PERF-01 + D13 VPS re-validation (CHANGELOG 2026-07-19) | engineering/performance |
| NFR-05 | C9  | obs/logging, /healthz                      | T-OBS-01..02 | engineering/integration |
| NFR-06 | C9  | obs/errors                                 | T-OBS-03 | — |
| NFR-07 | C3  | pricing/coster reconcile                   | T-PRC-05 (property) | engineering/testing |
| NFR-08 | Ops | scripts/backup.sh + restore drill          | T-OPS-02 (manual, logged) | engineering/integration |
| NFR-09 | Ops | docker-compose, Caddyfile, RUNBOOK         | T-OPS-03 (manual) | engineering/integration |
| NFR-10 | C  | runner via BackgroundTasks, status API      | T-API-02 | api/overview |
| NFR-11 | all | config, models (UTC), report display       | T-NFR-11 | — |
| NFR-12 | C9  | obs/ratelimit (user-else-IP key)           | T-NFR-12 | api/overview |
| NFR-13 | C   | runner queue admission, status API          | T-API-06 | api/overview |
| NFR-14 | C1,C9 | api error handlers, obs/errors            | T-API-07 | api/overview |
| NFR-15 | Ops,C3 | pricing/data/prices.yaml, scripts/pricing_age.py, CI | T-NFR-15 | concepts/pricing-data |
| X-01..05 | — | reviewer checklist item                   | REV-X (PR template) | limits, engineering/security |

Coverage rule: `pytest --cov=src/tokenops_cost_auditor` ≥ 85% lines on services/*,
100% on pricing/coster and rules/findings estimators (money math).
Matrix maintenance: any new FR requires a row here in the same PR.
