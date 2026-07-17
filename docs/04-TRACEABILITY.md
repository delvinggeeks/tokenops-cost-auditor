# Traceability Matrix — TokenOps Cost Auditor v1.0

Req → HLD component → LLD module(s) → Test ID(s). Test details in
05-TEST-PLAN.md. CI gate: every M-priority FR/NFR row must have ≥1 passing
test; matrix checked in review before merge to main.

| Req    | HLD | LLD module(s)                              | Tests |
|--------|-----|--------------------------------------------|-------|
| FR-01  | C1,C2 | web/upload, api/routes_upload, ingest/*  | T-ING-01..04, T-API-01 |
| FR-02  | C2  | ingest/normalizer                          | T-ING-05..07 |
| FR-03  | C2  | ingest/validator                           | T-ING-08..09 |
| FR-04  | C2  | cli.py                                     | T-CLI-01 |
| FR-05  | C3  | pricing/table, data/prices.yaml            | T-PRC-01..03 |
| FR-06  | C3  | pricing/coster                             | T-PRC-04..05 |
| FR-07  | C4  | rules/d1_oversized_model                   | T-RUL-D1-01..03 |
| FR-08  | C4  | rules/d2_missing_cache                     | T-RUL-D2-01..03 |
| FR-09  | C4  | rules/d3_prompt_bloat                      | T-RUL-D3-01..02 |
| FR-10  | C4  | rules/d4_retry_storm                       | T-RUL-D4-01..02 |
| FR-11  | C4  | rules/d5_unbounded_max_tokens              | T-RUL-D5-01..02 |
| FR-12  | C4  | rules/d6_chatty_loop                       | T-RUL-D6-01..03 |
| FR-13  | C4  | rules/findings, rules/registry             | T-RUL-00, T-RUL-EV-01 |
| FR-14  | C5  | report/model, render_json, render_pdf      | T-REP-01..04 |
| FR-15  | C5  | report/signer, web/report                  | T-REP-05..06 |
| FR-16  | C5  | report (synthetic fixture)                 | T-REP-07 (S) |
| FR-17  | C1  | web/auth (magic link)                      | T-AUTH-01..04 |
| FR-18  | C7  | payments/*, api/routes_webhooks            | T-PAY-01..05 |
| FR-19  | C1  | web/admin                                  | T-ADM-01..04 |
| FR-20  | C8  | mail/*                                     | T-MAIL-01 (S) |
| FR-21  | C6  | lifecycle/purge, lifecycle/auditlog        | T-LIF-01..03 |
| FR-22  | C4,C6 | rules/findings(EvidenceRef), persistence | T-LIF-04, T-RUL-EV-01 |
| FR-23  | C1  | web/templates/landing                      | T-WEB-01 |
| FR-24  | C2  | scripts/exporters/claude_code_export.py    | T-EXP-01..02 |
| FR-25  | C1  | main.py router mounting, api/*             | T-API-03 |
| FR-26  | C2  | api/routes_upload, persistence (idem keys) | T-API-04..05 |
| FR-27  | C7  | api/routes_webhooks, persistence (events)  | T-PAY-06..07 |
| FR-28  | C5  | report/model, render_json, render_pdf      | T-REP-08 |
| FR-29  | Ops | scripts/pricing_refresh.py                 | T-OPS-04 |
| NFR-01 | C4  | rules/* (import guard test)                | T-NFR-01 |
| NFR-02 | Ops | Caddyfile, config                          | T-OPS-01 (manual) |
| NFR-03 | C9  | obs/ratelimit                              | T-NFR-03 |
| NFR-04 | C2..C4 | runner (perf fixture 1M rows)           | T-PERF-01 |
| NFR-05 | C9  | obs/logging, /healthz                      | T-OBS-01..02 |
| NFR-06 | C9  | obs/errors                                 | T-OBS-03 |
| NFR-07 | C3  | pricing/coster reconcile                   | T-PRC-05 (property) |
| NFR-08 | Ops | scripts/backup.sh + restore drill          | T-OPS-02 (manual, logged) |
| NFR-09 | Ops | docker-compose, Caddyfile, RUNBOOK         | T-OPS-03 (manual) |
| NFR-10 | C  | runner via BackgroundTasks, status API      | T-API-02 |
| NFR-11 | all | config, models (UTC), report display       | T-NFR-11 |
| NFR-12 | C9  | obs/ratelimit (user-else-IP key)           | T-NFR-12 |
| NFR-13 | C   | runner queue admission, status API          | T-API-06 |
| NFR-14 | C1,C9 | api error handlers, obs/errors            | T-API-07 |
| NFR-15 | Ops,C3 | pricing/data/prices.yaml, scripts/pricing_age.py, CI | T-NFR-15 |
| X-01..05 | — | reviewer checklist item                   | REV-X (PR template) |

Coverage rule: `pytest --cov=src/tokenops_cost_auditor` ≥ 85% lines on services/*,
100% on pricing/coster and rules/findings estimators (money math).
Matrix maintenance: any new FR requires a row here in the same PR.
