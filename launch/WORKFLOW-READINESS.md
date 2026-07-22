# Workflow Readiness Audit — 2026-07-22

> **REMEDIATION COMPLETE (2026-07-22).** All four waves shipped and
> test-pinned. Criticals closed: Microsoft nOAuth (Wave 1), per-plan
> checkout (Wave 1). Integrity: idempotent free credit, SMTP-never-500,
> secret-key guard, public_base_url fallback (Wave 1). Domain-truth:
> statement false-zero, connect 401-vs-403, yesterday-tile unpriced,
> India-Scale asymmetry surfaced for ruling (Wave 2). UX completeness:
> real session invalidation, magic-link confirm interstitial, upload HTML
> errors + double-submit guard, daily-digest at-least-once + budget-path
> reconciliation (Wave 3). Test debt: true end-to-end tests for connect and
> alerts (Wave 4). Suite: 562 tests green. The scorecard below is the
> ORIGINAL audit; each finding's fix is in CHANGELOG v1.5.29–v1.5.33 and
> tests/test_readiness_wave*.py.


Founder order: validate every customer-facing workflow front-end → backend, with acceptance criteria and DoD. Method: 11 adversarial auditors, one per workflow, each tracing the full slice and checking implementation completeness, acceptance criteria, domain-truth of every external claim, unhandled states, real end-to-end test coverage, and data safety.

## Verdict

- Findings: 2 critical · 23 major · 25 minor
- Workflows audited: 11  ·  green: 0  ·  amber: 10  ·  red: 1
- Every workflow is wired end-to-end (all implemented_end_to_end=true) and passed data-safety (no corruption / cross-tenant-leak path in any slice).
- Gaps are concentrated in: domain-truth (false/misleading claims), unhandled error states, missing controls, and missing true end-to-end tests.

## [RED] Federated sign-in (Google / Microsoft / GitHub OAuth2)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Buttons render only when a provider has BOTH client id and secret, and each renders a working start->provider->callback->session flow with no dead buttons (config-gated per provider).
- Only provider-VERIFIED email addresses may claim/sign into an account -- no sign-in on an unverified or attacker-mutable email claim.
- CSRF: the callback accepts only the flow this browser started -- signed state pinned to an httponly cookie; forged or unpinned states refused.
- Exactly one signup comp credit per account regardless of provider or repeat logins (R-FREE-CONNECT one-meter law).
- Every provider endpoint URL and requested OAuth scope is real and identity-minimal (no fictional or over-broad scopes on the consent screen).
- Provider error / missing-code / unreachable / bad-secret states fail closed with a user-visible message and a server log -- never a partial sign-in.

**Findings:**
- **[critical/domain-truth]** Microsoft path trusts the mere PRESENCE of the userinfo `email` claim as proof of verification, but the /common Entra endpoint accepts tokens from ANY tenant and that claim is admin-settable and unverified (the nOAuth account-takeover class). The comment's 'presence-implies-verified' assertion is false. Attack: an attacker registers any Entra tenant, sets their account email to victim@corp.com (no ownership challenge), completes /auth/microsoft; graph userinfo returns email=victim@corp.com, _microsoft_email accepts it, and federation_callback issues a session AS the victim plus a comp credit on the victim's account.
  - evidence: `src/tokenops_cost_auditor/web/routes_auth.py:142 (_microsoft_email: no email_verified/xms_edov/tid check; /common endpoints L188-190). Contrast Google L137 and GitHub L157 which do check verification. Callback resolves the email at L326-334.`
- **[major/missing-test]** The suite enshrines the vulnerable Microsoft behavior as correct: it asserts sign-in SUCCEEDS on an email claim with no verification signal, so the test actively protects the defect and a proper fix (requiring email_verified/xms_edov) would break it -- false green.
  - evidence: `tests/test_federation.py:257 test_microsoft_email_claim_signs_in_with_one_credit (userinfo mock returns email with no email_verified; asserts 303 + one credit).`
- **[minor/data-safety]** First-login comp-credit grant has no idempotency guard; two concurrent callbacks for a brand-new email each read last_login_at is None and each insert a comp Payment, doubling the free-audit meter. Sequential replay is correctly blocked but concurrent is not.
  - evidence: `src/tokenops_cost_auditor/web/routes_auth.py:44 (first_login branch adds Payment) reached from callback L334; no unique constraint on (user_id, provider='comp'). Sequential guard tested at tests/test_federation.py:169.`

**Data safety:** Writes are keyed on the provider-derived email (get_or_create_user -> Payment.user_id) and the slice stores only counts/metadata (one comp Payment + a last_login stamp) -- no provider-API usage is written here, so the counts-only/read-only contract holds for Google and GitHub. But the Microsoft path breaks tenant isolation at the IDENTITY layer: trusting an unverified, attacker-controllable email claim lets an attacker be resolved to any existing user and receive a session for that account -- cross-user impersonation/takeover, not a corrupt write but a cross-leak of account access. A minor concurrency race can also double-write the signup credit on a new account.

## [AMBER] Email sign-up / sign-in (magic signin-link)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Magic link is single-use and dies on login (all earlier links invalidated by the last_login_at watermark)
- Magic link expires at the advertised 15 minutes
- Session cookie is HttpOnly + SameSite=Lax + Secure in production only
- Sign-in endpoint is rate-limited and does not leak account existence (identical response whether or not the account exists)
- Requesting a link either delivers it or tells the user delivery failed - no silent 500 dead-end
- A single-use link survives corporate email prefetch/scanning so the target work-email user can actually complete sign-in

**Findings:**
- **[major/unhandled-state]** GET /auth/verify consumes the single-use link on the first request, so an email security scanner or client that prefetches the link (Outlook SafeLinks, Proofpoint, Gmail) burns it before the human clicks; the scanner's GET stamps last_login_at and the real click then fails verify_magic_token with 'already used' (400). This locks out exactly the scanned corporate work-email buyer the product markets to. There is no interstitial POST-to-confirm.
  - evidence: `src/tokenops_cost_auditor/web/routes_auth.py:75-96; src/tokenops_cost_auditor/web/auth.py:43`
- **[major/unhandled-state]** request_magic_link commits the DB request (line 65) then calls mail.magic_link with NO try/except (line 67). If SMTP is unreachable/misconfigured in prod the exception propagates as a 500: the user never sees the 'Check your email' page, no link arrives, and there is no support affordance - yet the audit log already recorded the request. The federation callback wraps its httpx calls (321-324); the magic-link send does not.
  - evidence: `src/tokenops_cost_auditor/web/routes_auth.py:66-72`
- **[major/data-safety]** The first-login free-audit comp credit is not idempotent. first_login is derived from reading user.last_login_at==None (line 95); two concurrent first-login verify GETs (scanner prefetch + human click, or a double-click) each read None in separate sessions before either commits and both insert Payment(provider='comp', amount=0). No unique constraint on (user_id, comp) guards it, so a user can be granted two free audits. Scoping is otherwise correct (writes are per user_id/email; no cross-tenant leak) and the slice honors counts-only - it persists only last_login_at, a $0 Payment, and audit rows.
  - evidence: `src/tokenops_cost_auditor/web/routes_auth.py:44-48`
- **[minor/inconsistency]** signin.html's own comment (lines 8-11) states 'NO SSO buttons - a button that does nothing is a promise', yet the template renders Google/Microsoft/GitHub federation buttons (44-60). The buttons are NOT dead (enabled_federations emits only fully-credentialed providers and federation_start 404s otherwise), so this is a stale/contradictory comment, not a functional defect. Domain-truth note: the rendered OAuth scopes (google/microsoft 'openid email', github 'user:email') are all REAL, valid scopes with verified-only email extraction - this workflow does NOT repeat the connect-wizard phantom-scope defect.
  - evidence: `src/tokenops_cost_auditor/web/templates/signin.html:8-11`

**Data safety:** Every write is scoped to the owning user: get_or_create_user resolves by lowercased email (repo.py:26-32), Payment is written with user_id=user.id, last_login_at is set on that user only, and audit rows are subject-scoped by email. No cross-tenant read or write path exists and the slice honors the counts-only/read-only contract (it persists only a login timestamp, a $0 comp Payment, and audit-log rows - no provider data, no prompt/completion text). The one integrity gap is non-idempotent same-user comp-credit issuance under concurrent first-login (Finding 3): it can double-credit a single user but cannot corrupt or leak another tenant's data.

## [AMBER] Monthly savings statement (build → gating → email → archive)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- An authenticated owner can view the current-month preview, see the list of issued statements, and open any archived statement; unauthenticated gets 401 (routes + templates + TestStatementPages).
- "Email it to me now"/"Send it again" delivers the archived artifact to the owner's address at-most-once, and a statement already sent is frozen (archive() never rewrites a sent row).
- Every figure is R-Q9-honest: the verified headline is re-audit-proven over >=7 days, and identified / customer-reported / equiv-spend sit in their own labelled sections and are never summed.
- The monthly batch archives unconditionally for all plans and emails per R-STMT-GATING (paid always; free only on a month with activity), with per-user failure isolation.
- All reads/writes are scoped to the owning user_id, cross-tenant statements are unreadable, and the body stores dollars/counts only (no prompt/completion text, FR-22).
- Customer-facing claims are true/verifiable and error/provider-unreachable states degrade gracefully rather than returning an uncaught 500.

**Findings:**
- **[major/domain-truth]** The statement tells the bill-signer "Nothing outstanding — every finding has been actioned." whenever identified_usd==0, which is false when the user has zero findings at all — nothing was ever actioned.
  - evidence: `src/tokenops_cost_auditor/services/statements/build.py:171`
- **[major/unhandled-state]** Interactive POST /statements/{period}/send has no try/except; if request.app.state.mail.alert raises (SMTP unreachable) the owner gets an uncaught 500. The batch job guards this exact call per-user (monthly_statements.py:65) but the interactive route does not.
  - evidence: `src/tokenops_cost_auditor/web/routes_statements.py:97`
- **[minor/unhandled-state]** Double-submit/race on POST /send: two concurrent first-time sends both build+archive, the second violating uq_statement_period (IntegrityError→500); two concurrent resends both pass send()'s sent_at-is-None check and deliver a duplicate email. No row lock or idempotency guard.
  - evidence: `src/tokenops_cost_auditor/web/routes_statements.py:89`
- **[minor/inconsistency]** send() sets sent_at and returns True even when the mail object exposes no callable alert (deliver is None): a statement can be marked "Sent" with no email actually delivered under a misconfigured adapter.
  - evidence: `src/tokenops_cost_auditor/services/statements/build.py:245`
- **[minor/missing-test]** The e2e (TestStatementPages) covers only the happy path; no test exercises the interactive send path under a mail-adapter failure, nor the identified==0 "every finding has been actioned" wording, so the two customer-facing gaps above are untested.
  - evidence: `tests/test_statements.py:263`

**Data safety:** Safe. Every read and write is scoped to the owning user_id: Statement carries user_id with UniqueConstraint(user_id, period); build/archive/send/should_email all filter on user.id; savings.compute scopes by user_id + period. Cross-tenant read returns 404 (test_cross_user_statements_are_not_readable). No provider API calls occur in this slice (read-only platform honored); the only outbound side effect is emailing user.email its own archived body. body_text stores dollars/counts/hashes only — no prompt/completion text (FR-22 honored). No corruption/delete/cross-leak path found; the only integrity gap is finding #4 (sent_at set without delivery), which does not cross tenants.

## [AMBER] Connect a provider (admin-key wizard → validate → first pull → first audit)
impl_end_to_end=True · dod_met=False · has_e2e_test=False

**Acceptance criteria:**
- Every external claim the wizard makes (provider console URL, key type/authority, read-only scope, 'we never read prompts', backfill/cadence timings) is true and verified against provider reality.
- Each validation verdict maps to the true provider condition: valid+scoped=ok, valid+unscoped=no_scope, invalid/revoked key=clear 'bad key', unreachable=degrade-and-save.
- First pull + first audit is guaranteed to complete on every plan, or the user is told it didn't and given a retry — the 'dashboard fills within minutes' promise must not silently fail.
- All writes scoped to the owning user_id; provider access is read-only (GET, counts only, FR-22); revoke deletes ciphertext and is ownership-checked.
- A double-submit cannot create two active connections or two first-pulls.
- A test exercises the whole path: wizard submit → real pull → real audit → persisted Audit + report.json.

**Findings:**
- **[major/domain-truth]** An invalid/revoked key (HTTP 401) is reported to the user as no_scope with the copy 'The key works, but it isn't allowed to read usage' — a false statement that misdiagnoses a typo'd key as a permissions problem and sends the user hunting for a scope box that will not fix it.
  - evidence: `src/tokenops_cost_auditor/services/connectors/openai_usage.py:70 (401 AND 403 both raise ConnectorAuthError; same in anthropic_usage.py:79) → validate.py:95 maps ConnectorAuthError to VERDICTS[NO_SCOPE], whose detail (validate.py:59) claims 'The key works, but it isn't allowed to read usage.'`
- **[major/unhandled-state]** The free-plan first pull+audit is a fire-and-forget daemon thread that swallows ALL exceptions and has no retry, yet the UI promises 'your dashboard fills within minutes / nothing else for you to do'. The scheduler explicitly skips free sources, so a failed kickoff (provider hiccup or a worker restart mid-thread) leaves the dashboard permanently empty with no error surfaced and no way to re-trigger — the credit is preserved but stranded.
  - evidence: `src/tokenops_cost_auditor/web/routes_sources.py:268 (bare except → log only) + :271 (daemon Thread); schedule.py:49-56 (due_pulls filters out non-scheduled_audits/free plans); promise text in help_registry.yaml step3_body + _wizard_verdict.html:17.`
- **[major/missing-test]** No test exercises the workflow end-to-end. Every wizard test monkeypatches _kickoff_first_pull (or forces run_pull to throw) and FakeHTTP returns empty data, so the real path connect → run_pull → run_source_audit → persisted Audit + report.json is never driven; no test asserts an Audit row or report.json exists after a connect. run_pull/run_source_audit are covered only as isolated units.
  - evidence: `tests/test_connect_wizard.py:132-136 and :156-158 (kickoff/pull stubbed); grep for 'report.json'/'Audit)' in the two connect tests returns nothing.`
- **[minor/inconsistency]** The at-limit empty-state CTA labelled 'Manage sources' links to /settings, but the sources list where a user actually revokes a connection to free a slot is served at /sources — the user is sent to the wrong page to perform the exact action the message instructs.
  - evidence: `src/tokenops_cost_auditor/web/templates/app/connect_wizard.html:25 (action_href='/settings') vs routes_sources.py:50 (GET /sources renders app/sources.html with the revoke controls).`
- **[minor/data-safety]** The plan-cap and provider-idempotency guards serialize on SELECT ... with_for_update, which is a no-op on SQLite; under genuine concurrency on SQLite two connects could both pass the re-check and create two active sources of one provider. The double-submit test passes only because TestClient issues the two POSTs sequentially. The guarantee is Postgres-only (documented in-code).
  - evidence: `src/tokenops_cost_auditor/web/routes_sources.py:179 and :294 (with_for_update, 'no-op on SQLite'); tests/test_connect_wizard.py:299 exercises sequential, not concurrent, submits.`

**Data safety:** Data-safety is sound. Every write is scoped to the owner: Source.user_id on connect (routes_sources.py:192,308), Audit(user_id=source.user_id) in source_audit.py:137, and revoke_source rejects non-owners with 404 (routes_sources.py:328). Provider access is strictly read-only — openai_usage/anthropic_usage issue only GET and parse counts (num_model_requests/tokens), never text (FR-22 honored); revoke nulls the ciphertext (routes_sources.py:331). No cross-tenant read, delete, or overwrite path found. Two caveats, neither a leak: (1) the plan-cap/idempotency serialization relies on SELECT ... with_for_update (routes_sources.py:179,294), which is a no-op on SQLite — the guarantee is Postgres-only; (2) _kickoff_first_pull re-loads the Source by id in a daemon thread without an ownership re-check, but the id is that of the just-created owned source, so no cross-tenant exposure.

## [AMBER] Dashboard (widgets, yesterday tile, freshness, account menu, tour)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Unauthenticated GET /dashboard returns 401; every widget renders both on the page and standalone at /dashboard/w/{key}, and one tenant's numbers never appear for another (test_dashboard 01/03/04/05 + test_daily_loop) — MET.
- Zero-state shows no fabricated numbers ($0.00 absent) and teaches the next action ('Connect a source', 'Your first audit fills this in') — MET (test_02).
- Every interactive shell control resolves to a live endpoint with no dead link: account-menu Log out -> POST /auth/logout (router prefix /auth + POST /logout), Replay tour -> /tour/replay (303), Skip tour -> /tour/dismiss persisting user.tour_dismissed_at — MET.
- Every user-facing number states an accurate provenance and no excluded amount is dropped silently — NOT MET: the Yesterday tile discards daily._rate_cost's `unpriced` set (metrics.py:281-298) while still labelling itself 'priced on the verified rate card'; the email digest discloses the exclusion, the tile does not.
- The topbar freshness stamp must not contradict the tiles below it — NOT MET: freshness is derived only from the latest status=='done' Audit (routes_dashboard.py:72-77), so a paid user with pulled daily usage but no finished audit sees 'No data yet — connect a source' while the Yesterday tile shows real spend.
- The recurring 'Daily usage pulls' that feed the tile actually run in production — NOT DEMONSTRABLE: scripts/scheduler_tick.py is documented as the hourly Ofelia entrypoint but no ofelia/cron/systemd wiring exists in deploy/ (only README.md + tf/*.tf) or .github (only a CI perf cron), so after the single connect-time pull the tile may never refresh.

**Findings:**
- **[major/inconsistency]** Yesterday tile silently drops models that have no verified rate while still claiming 'priced on the verified rate card'; daily.spend_between returns an `unpriced` set (daily.py:80-82) that run_digests surfaces as an exclusion note but yesterday_spend ignores, so the tile under-reports spend with no asterisk. A customer whose biggest model isn't in the pinned rate card sees a falsely low 'Yesterday' number.
  - evidence: `src/tokenops_cost_auditor/services/dashboard/metrics.py:281`
- **[major/domain-truth]** The tile's provenance 'Daily usage pulls · priced on the verified rate card' implies an automatic recurring pull, but the only scheduler entrypoint (scripts/scheduler_tick.py, self-described 'Ofelia entrypoint (hourly)') has no ofelia/cron/systemd invocation anywhere in the repo's deploy config (deploy/ holds only README.md + tf/*.tf; .github has only a CI perf cron). Failure: in production, after the one connect-time run_pull, no further pulls land, the tile stays empty/stale, and the 'daily' promise is hollow — unverifiable from the repo.
  - evidence: `scripts/scheduler_tick.py:1`
- **[minor/inconsistency]** Topbar freshness is computed only from the latest status=='done' Audit, but the Yesterday tile is fed by Source usage pulls; a paid user with pulled daily data but no completed audit gets 'No data yet — connect a source or upload a log file' in the header directly above a tile showing real dollars. The two surfaces contradict each other.
  - evidence: `src/tokenops_cost_auditor/web/routes_dashboard.py:73`
- **[minor/unhandled-state]** capture_feedback does select-then-insert with no handling of the uq_feedback_finding unique constraint (models.py:248). Single-request idempotency is fine, but a genuine double-submit race (two concurrent POSTs, both seeing no existing row) makes the second INSERT raise IntegrityError -> unhandled 500 instead of an idempotent no-op. No data corruption (constraint holds), but an ungraceful error.
  - evidence: `src/tokenops_cost_auditor/web/routes_dashboard.py:430`

**Data safety:** Data safety is sound for this slice. Every read and write is scoped to the resolved user_id: get_or_create_user derives the tenant from the auth dependency, _owned_audit and _drawer_context re-check audit.user_id == user.id (returning 404 on mismatch), and capture_feedback/tour/next_audit/yesterday all filter by user_id. The cross-user leak test (test_05) passes: another user's page omits the $999 figure and the finding drawer 404s. FindingFeedback carries a uq(audit_id, finding_id) constraint so re-votes update in place rather than stacking. The slice honors read-only-with-counts: the Yesterday tile prices SourceUsage token counts against the pinned rate card via daily._rate_cost; no prompt/completion text is read or stored (FR-22 respected). No path here can delete or cross-leak another tenant's rows; the only concurrency exposure is a 500 (not corruption) on a feedback double-submit race.

## [AMBER] Alerts (rule config → evaluation on scheduler tick → email → history)
impl_end_to_end=True · dod_met=False · has_e2e_test=False

**Acceptance criteria:**
- Path connected end to end: alerts.html form → POST /alerts → AlertRule persisted → scheduler_tick.py → schedule.tick → dispatch.run_all → rules.evaluate → AlertEvent + mail.alert → GET /alerts history. MET — every layer exists and is wired (scheduler_tick.py:32 calls tick; schedule.py:131 calls run_all).
- Every user-facing claim is true (weekly audit cadence, 'at most one email per rule per audit', observe-only 'never pause/cap'). MET — AUDIT_EVERY=7d (schedule.py:30); dedup by (rule,audit_id) (rules.py:101); enforcement forbidden by import-guard test T-ALR-05 (test_alerts.py:234) + body-promise test (test_alerts.py:256).
- Fires at most once per rule per audit; a mail failure never re-sends nor loses earlier alerts. MET — record-before-send + per-event commit (dispatch.py:57-64); tests test_sends_once_per_audit, f2, f4.
- All writes scoped to owning user_id, counts/figures only, no cross-tenant leak. MET — see data_safety_note.
- Plan gating honest at BOTH server surfaces (POST 403 + GET upsell), test-covered. PARTIALLY MET — behavior implemented (routes_alerts.py:135, :68) but no web-layer test; only dispatch-layer non-evaluation is tested (test_alerts.py:485).
- A real end-to-end test walks config→tick→email→history in one path. NOT MET — the seam is only covered in disjoint segments; schedule.tick is exercised solely with run_all mocked to raise (test_alerts.py:435).

**Findings:**
- **[major/missing-test]** No single test traverses the whole path (POST config → real schedule.tick → email → /alerts history render); the integration seams are only covered as disjoint units.
  - evidence: `tests/test_alerts.py:435`
- **[minor/unhandled-state]** soft_budget enabled with a blank threshold is silently inert: save stores enabled=True/threshold=None (routes_alerts.py:150-158), _default_threshold returns None for soft_budget (routes_alerts.py:54), and evaluate requires threshold is not None (rules.py:181), so the user believes a budget alert is armed but nothing ever fires and no UI warns.
  - evidence: `services/alerts/rules.py:181`
- **[minor/missing-test]** Web-layer plan gating is untested: POST /alerts 403 for a non-watching plan and the GET free-plan upsell branch have no test; only dispatch-layer non-evaluation is asserted.
  - evidence: `web/routes_alerts.py:135`
- **[minor/inconsistency]** Alert email subjects/bodies hardcode USD '$' formatting while the /alerts page and billing render the viewer's currency (plans.viewer_currency); an INR viewer receives '$1,400/mo' emails but sees ₹ everywhere else. Figure is USD-canonical so not a false claim, but presentation drifts.
  - evidence: `services/alerts/rules.py:118`
- **[minor/unhandled-state]** Concurrent double-submit of POST /alerts can violate uq_alert_user_rule: both requests read an empty `existing` map and both session.add an AlertRule for the same (user_id, rule); the unique constraint then raises IntegrityError with no handler → 500. Low likelihood on a single-user config page but unhandled.
  - evidence: `web/routes_alerts.py:156`

**Data safety:** Sound and tenant-scoped. POST /alerts filters AlertRule by user_id and writes user_id=user.id (routes_alerts.py:72,158). dispatch writes AlertEvent user_id=user.id (dispatch.py:58) and evaluate scopes every read — AlertRule/AlertEvent by user.id (rules.py:84-92), Audit by user.id (rules.py:71), FindingRow by the user's own latest/previous audit id (rules.py:147,156). run_all iterates all users but each evaluate is per-user scoped; emails go to that user's own address. Honors read-only/counts-only: AlertEvent.detail (models.py:275) stores only figures (before/after/pct/usd/budget) — no prompt/completion text, no provider mutation. No corruption, deletion, or cross-tenant leak path found in this slice.

## [AMBER] Daily digest + budget staging + yesterday tile (R-DAILY-LOOP)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Both surfaces wired end to end (dashboard tile + partial route + daily email via scheduler) with a real budget-setting UI (/alerts) — no dead-ends
- Priced spend is byte-identical across tile, digest and audit (one rate formula, uncached input + cache_read + output vs verified card)
- Digest is delivered at most once per paying customer per UTC day, a zero-spend day stays silent yet stamps, and delivery is reliable (a transient mail failure must not permanently drop the day)
- Budget staging fires each 50/80/100 stage once per month and escalates, WITHOUT a second code path double-notifying the same customer under a different budget definition
- Every number/claim shown to the customer is true and verifiable, including disclosure of models excluded for lack of a verified rate — on the tile as well as the email
- Every write is scoped to the owning user_id; the slice stays read-only/counts-only against provider data

**Findings:**
- **[major/unhandled-state]** Digest stamp + budget AlertEvent are committed BEFORE the email is sent, so a transient mail failure permanently drops that day's digest (and silently consumes the budget stage) with no retry.
  - evidence: `src/tokenops_cost_auditor/services/connectors/daily.py:226-249`
- **[major/inconsistency]** SOFT_BUDGET is notified by TWO independent paths in the same tick with divergent semantics: daily.run_digests stages 50/80/100 on ACTUAL month-to-date spend, while alerts/rules.py fires 'past your budget' on PROJECTED run-rate from the latest audit — one customer, one budget, can receive two contradictory emails sharing one rule identity and AlertEvent stream.
  - evidence: `src/tokenops_cost_auditor/services/connectors/daily.py:171-238 vs src/tokenops_cost_auditor/services/alerts/rules.py:180-196`
- **[major/missing-test]** Tests cover only happy paths (delivery, at-most-once, zero-spend, single-path budget escalation, tile numbers). No test exercises mail-send failure after the stamp commit, unpriced-model handling in digest or tile, or the interaction between the digest budget stage and the alerts-dispatch soft_budget — the three real defects above are all untested.
  - evidence: `tests/test_daily_loop.py:105-317`
- **[minor/inconsistency]** The yesterday tile computes DaySpend.unpriced but drops it: yesterday_spend never passes it to the template and _yesterday.html has no exclusion notice, so on a day with an unpriced model the tile silently understates spend while the email discloses the exclusion — contradicting the module's own 'no two surfaces ever disagree' claim.
  - evidence: `src/tokenops_cost_auditor/services/dashboard/metrics.py:287-298`
- **[minor/domain-truth]** The shipping verified rate card carries 'claude-fable-5' ($10/$50/M, cache_read $1) under a vendor source_url, but the test docstring itself calls it 'the fixture model claude-fable-5' and config.py aliases it to claude-opus-4-8 (which is priced differently, $5/$25); a fixture model presented as vendor-verified is rate-card hygiene debt, though real customer usage carries real model strings so no live customer surface depends on it.
  - evidence: `src/tokenops_cost_auditor/services/pricing/data/prices.yaml:27-32`

**Data safety:** Data-safe. Every write is owner-scoped: users.last_daily_digest_at is set on the iterated user, AlertEvent is written with user_id=user.id, and all reads go through spend_between which joins Source on Source.user_id==user_id; the widget route resolves the user via the authenticated current_user dependency (prod = magic-link session cookie; X-User-Email is a non-prod shim, 401 otherwise). No cross-tenant query, no unscoped write, no delete. The slice honors read-only/counts-only: it reads SourceUsage token counts and prices only and makes no provider network call. Residual (low): the at-most-once stamp guards concurrency only under serial cron execution — two overlapping ticks could both read last=None and double-send, but the single hourly ofelia tick makes this practically unreachable.

## [AMBER] Settings → Close account (purge uploads + revoke keys + cancel subscription + sign out + audit log)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Typed confirmation phrase 'CLOSE MY ACCOUNT' gates the action; any near-miss mutates nothing (routes_settings.py:164) — MET (test_wrong_phrase_closes_nothing).
- On confirm: uploads purged, keys revoked + ciphertext deleted, subscription cancelled locally, account.closed audit entry with provider_cancellation_required, session cookie cleared — MET (test_the_page_promises_are_all_kept).
- Every user-facing promise on the page is literally true (domain-truth) — MOSTLY MET; copy is carefully honest, but see session-kill and 1-business-day gaps.
- The 'you will not be charged again / within 1 business day' provider-cancellation promise has a durable non-lossy carry to the founder — PARTIALLY MET; carried by a lossy 24h-window digest only.
- Closing kills the account's sessions ('session kill') not just the acting browser cookie — NOT MET; stateless cookies, no revocation.
- Every write scoped to owner user_id, no cross-tenant leak, no provider-side writes — MET (code scoping + cross-tenant purge test).

**Findings:**
- **[major/missing-control]** 'Session kill' is not real. close_account only calls response.delete_cookie on the acting browser (routes_settings.py:216); sessions are stateless signed cookies and verify_session (web/auth.py:52-58) checks only signature + TTL — never last_login_at or any revocation/epoch. close_account never bumps last_login_at, so any concurrent session on another device stays valid for session_ttl_days after 'close'. FAILURE: user closes account because a shared/compromised second device still has access — that device's cookie keeps working (views archived statements/reports, hits authed routes) with nothing to revoke it. The workflow is named 'session kill' and the test docstring (test_saas_basics.py:158) claims it, yet only the current cookie is cleared.
  - evidence: `src/tokenops_cost_auditor/web/routes_settings.py:216`
- **[major/missing-control]** The on-page money promise 'We close the payment-provider record within 1 business day — you will not be charged again' (settings.html:117-119) is carried ONLY by a 24h-window digest line (daily_digest.py:102-108, ts >= now-24h) with no durable pending-cancellation queue and no acknowledgement. Each run re-queries a fresh 24h window, surfacing a closure exactly once. FAILURE: the cron sidecar misses a run (deploy/error/host down) or the founder doesn't act that morning — the account.closed task permanently drops out of all future digests, the provider record is never cancelled, and the customer is billed next cycle, silently contradicting the guarantee. test_the_digest_carries... (test_saas_basics.py:201) only proves the same-window happy path, not durability across a missed run.
  - evidence: `scripts/daily_digest.py:102`
- **[minor/unhandled-state]** No success confirmation. On success close_account redirects to '/' (public landing) logged out (routes_settings.py:215). settings_page accepts a 'closed' param but the template renders it only for failure (settings.html:130, closed < 0) — there is no closed>=0/success branch anywhere. FAILURE: user types the phrase, clicks Close, and is dropped on the marketing site with zero acknowledgement it worked; cannot tell success from error, may re-submit or email support.
  - evidence: `src/tokenops_cost_auditor/web/routes_settings.py:215`

**Data safety:** Data-safe. Every write in close_account is scoped to the resolved owner: audits filtered by Audit.user_id==user.id (routes_settings.py:168-178), sources by Source.user_id==user.id (185-191), subscription by Subscription.user_id==user.id (196-198); purge_one acts only on those pre-scoped audits and rmtree targets that audit's own upload dir. Cross-tenant isolation of the purge primitive is proven by test_purge_is_scoped_to_the_signed_in_account (test_settings.py:141-167). No provider-side writes — closure only nulls local key ciphertext and cancels the local subscription row, honoring the read-only/counts-only contract; the audit log is append-only (auditlog.py has no update/delete). No corruption or cross-leak path found; double-submit is idempotent (upload_path/purged_at already cleared, sub already cancelled so provider_cancellation is not re-flagged). Gap (not a leak): close_account has no dedicated cross-tenant test of its own.

## [AMBER] Upload a log file → audit → report (signed-in customer path)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- Happy path connected end to end: signed-in user uploads a valid file, audit runs to done, report.json/html/pdf are persisted, and a signed report link is emailed and retrievable at /r/{token} — MET (runner.py:154-202, routes_report.py:18-29, test_upload_and_complete + test_report_web).
- Payment-required state is presented to the BROWSER user as a usable payment page/link per the on-page promise, not raw JSON — NOT MET (402 renders JSON envelope; routes_upload.py only returns HTML on success).
- Pre-pipeline input rejects (bad extension 400, too-large 413) are surfaced to the browser user as readable errors — NOT MET for browser (JSON); post-pipeline <95%-valid failure IS surfaced on the progress page (MET).
- Ownership isolation: a user can only see/poll/retrieve their own audit — MET (get_user_audit + _owned_audit re-checked on every poll; test_other_user_cannot_see_audit).
- No double-charge / double-run on an accidental UI resubmit — NOT MET (browser form sends no Idempotency-Key and has no submit-disable; two clicks = two audits, two credits claimed).
- Retention promise honored — MET with minor slack (purge_after_days=7, daily cron, created_at fallback on failures; config.py:27, purge.py:31-37).

**Findings:**
- **[major/unhandled-state]** Every non-success outcome of the upload form (402 no-credit, 400 bad-extension, 413 too-large) is returned to the browser as a raw JSON error envelope, because the only HTML redirect in create_audit fires on the 201 success path; all /api/ errors go through error_envelope (JSON). A signed-in user whose free credit is spent, or who selects a .txt/oversized file, lands on a raw JSON blob. This directly contradicts the on-page promise 'If a payment is required, we'll show you the payment link first' (upload.html:49) — the link is buried inside a JSON detail string, never shown as a page.
  - evidence: `src/tokenops_cost_auditor/api/routes_upload.py:150-152 (HTML only on 201) + src/tokenops_cost_auditor/main.py:61-72,196-197 (JSON envelope for /api/*) vs src/tokenops_cost_auditor/web/templates/app/upload.html:47-50`
- **[major/missing-control]** Idempotency/double-submit protection is unreachable from the only UI that exists. The Idempotency-Key is an HTTP header settable only by API clients (routes_upload.py:88); the browser form is a plain native POST with no key and no submit-disable JS. A double-click or retry submits two POSTs, creating two audits and atomically claiming two credits — claim_credit prevents double-spending ONE credit but not consuming two. For a paying multi-credit user this silently burns real money and starts two runs for one intended audit; FR-26 idempotency does not protect the browser path.
  - evidence: `src/tokenops_cost_auditor/api/routes_upload.py:88,109-116 + src/tokenops_cost_auditor/web/templates/app/upload.html:31-46`
- **[minor/missing-test]** No test exercises the browser error branches of the upload workflow. test_pipeline_theater covers only the 303 success redirect (test_pipeline_theater.py:145-166); the raw-JSON-to-browser states (402/400/413 with Accept: text/html) are untested and can regress silently. The full delivery leg (upload → email → /r/{token} retrieval) is verified only across three separate test files with hand-built fixtures, not in one continuous end-to-end assertion.
  - evidence: `tests/test_pipeline_theater.py:145-166; tests/test_api.py:52-63; tests/test_report_web.py:114-123`
- **[minor/domain-truth]** Retention copy is slightly overbroad. 'Deleted within 7 days / nothing retained beyond 7 days' (upload.html:28,43): purge runs daily against a 7-day window, so a raw file can persist up to ~8 days worst case; and purge deletes ONLY the raw upload directory — the rendered report.html/report.pdf and derived count aggregates are retained indefinitely (purge.py docstring 6-7). The claim is defensible for the raw file but a skeptical reader would read 'nothing retained' as covering the report too.
  - evidence: `src/tokenops_cost_auditor/services/lifecycle/purge.py:1-9,31-37 + src/tokenops_cost_auditor/web/templates/app/upload.html:26-44`
- **[minor/domain-truth]** The 'connect' tab embedded on the upload page claims 'We read your usage reports directly from OpenAI or Anthropic with one key, used read-only on our side' (_get_logs_tabs.html:10-12). Provider API keys are full-access; 'read-only' is a promise about internal behavior, not a provider-enforced scope — the same phrasing shape as the prior shipped defect (a non-existent 'read usage' scope). Verify the connector actually cannot mutate before this copy is trusted; it advertises a separate workflow on this page.
  - evidence: `src/tokenops_cost_auditor/web/templates/_get_logs_tabs.html:10-12`

**Data safety:** Sound. Every write is scoped to the owning user_id: create_audit(session, user.id) (routes_upload.py:109); claim_credit UPDATEs Payment WHERE user_id AND audit_id IS NULL, atomic + rowcount-checked (payments/base.py:37-66); status/progress/poll all enforce ownership via get_user_audit / _owned_audit re-checked on every 2.5s poll (routes_dashboard.py:210,240); upload and report dirs are keyed by opaque audit uuid. The /r/{token} report link is gated by an HMAC-signed, 30-day-expiring token rather than user_id — intended shareable-link model (FR-15), not a leak. No cross-tenant write or delete path found; the platform is read-only against providers and stores counts only (runner.aggregate + evidence samples capped at 20, token counts). Ownership isolation is regression-tested (test_api.py:65 test_other_user_cannot_see_audit).

## [AMBER] Report generation & viewing (model → web + PDF + signed URL)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- A valid signed token serves the web report (200 HTML) and the PDF (200 application/pdf); tampered/expired/wrong-secret/missing-file all return a user-safe 404 with no internals leaked — MET (routes_report.py:23-29,37-46; tests TestTREP0506, TestWebReportRoute).
- Report numbers are assembled once in ReportModel.build and never recomputed by a renderer; report.json is deterministic and carries EVERY finding while web/PDF show the top-50 by monthly impact with an explicit note — MET (model.py:91-144, render_json.py:63-69, run_all sorts by -impact registry.py:37, D11 tests).
- Every user-facing claim (pricing 'human-verified <date>', 'purged 7 days after', 'expires in 30 days', 'never stored/trained') is backed by real current behavior — PARTIALLY MET: purge job exists (services/lifecycle/purge.py), dates match config today, but strings are hardcoded and decoupled from settings (finding 3).
- The signed report URL reaches the customer as an absolute, clickable link and that delivery is tested — NOT MET (findings 1 & 4).
- The signed-URL signature is a real access control in production, i.e. no default/forgeable secret — NOT MET (finding 2).

**Findings:**
- **[major/missing-control]** Report-ready email builds the link as base_url+/r/{token} where base_url=app_base_url (config.py:67) defaults empty and smtp.py:60 has NO fallback — unlike main.py:127 and daily.py:207 which fall back to https://tokenops-cost-auditor.com. Email is the sole delivery of the signed URL (no /r/ link in any owner-dashboard template). FAILURE: operator sets smtp_host (main.py:100) but leaves app_base_url empty → every report-ready email ships a relative, unclickable link '/r/{token}' and the customer cannot reach their report.
  - evidence: `src/tokenops_cost_auditor/services/mail/smtp.py:60`
- **[major/missing-control]** No startup guard rejects the default secret_key 'dev-secret-change-me'; the itsdangerous signature is the report's only access control and the audit_id is printed plaintext on every report page (_report_body.html:7). FAILURE: prod deploy that forgets to override secret_key (only a runbook comment warns) → signed URLs become forgeable — anyone who learns an audit_id mints a valid token and reads another tenant's report; the signed-URL protection is void.
  - evidence: `src/tokenops_cost_auditor/config.py:18`
- **[minor/inconsistency]** User-facing retention/expiry text is hardcoded and decoupled from the settings that drive behavior: DATA_HANDLING says 'purged 7 days after' vs settings.purge_after_days (config.py:27), email says 'expires in 30 days' vs settings.report_url_expiry_days (config.py:130). Values match today. FAILURE: operator changes either setting → report/email keep promising 7/30 days, silently misstating data handling to the user.
  - evidence: `src/tokenops_cost_auditor/services/report/model.py:49`
- **[minor/missing-test]** The E2E test re-signs its own token (test_report_web.py:113) instead of asserting the link the runner actually emits (runner.py:202 → smtp.py:60), so the generation→email→absolute-URL handoff — the real customer entry point — is never exercised. FAILURE: a broken/relative emailed link (finding 1) passes the whole suite because no test inspects the email body.
  - evidence: `tests/test_report_web.py:113`
- **[minor/unhandled-state]** report.json/report.html are written (runner.py:154-158) before render_pdf (runner.py:159); if render_pdf raises (WeasyPrint OOM — the exact failure render_cap guards against) the exception is caught at runner.py:103 and the audit is marked failed, but the already-written report.html/json are orphaned on disk. FAILURE: PDF render blows up → audit=failed, no email, partial artifacts linger until the audit's retention window. Not a leak; a consistency/housekeeping gap.
  - evidence: `src/tokenops_cost_auditor/services/runner.py:159`

**Data safety:** Write path is clean: all derived writes are owner-scoped to audit_id, which is bound to user_id on the Audit row — FindingRow/CallAggregate insert-after-delete keyed on audit_id (runner.py:165-184), purge per-audit (purge.py). Read-only-vs-provider + counts-only honored: evidence rows carry token counts/notes only, no prompt/completion text persisted, and autoescape is on for the shared Jinja env (render_pdf.py:18-21) so log-derived model/note fields cannot inject stored XSS. The residual cross-leak risk is NOT in the write path but in access control: the signed URL is a bearer capability with no revocation before its 30-day expiry and no code guard against the default secret_key (config.py:18) that would make every token forgeable — that combination is the only way this slice could disclose another tenant's report (finding 2).

## [AMBER] Billing & regional pricing (plans, currency detection, launch cohorts, checkout, dunning)
impl_end_to_end=True · dod_met=False · has_e2e_test=True

**Acceptance criteria:**
- A signed-in user can select any paid plan and be sent to a checkout that charges THAT plan's displayed price/currency — NOT met: one static hosted link per provider is shared by Pro and Scale, the selected plan is never conveyed, and Stripe sub metadata defaults plan to 'pro'.
- The price shown equals the price the provider will actually charge (launch-vs-list, currency) — NOT met: the launch->list flip is code-display-only against a manually-updated static link, and the India '$' display value does not reconcile with the '₹' charge.
- Dunning ladder past_due->read_only(day7)->cancelled(day21) is a pure idempotent function that emails once per rung and deletes nothing — MET (tested, test_subscriptions.py:185-231).
- Payment webhooks are signature-verified, timestamp-bounded (FR-27), deduped by event id, never double-applied; unauthenticated /billing returns 401 — MET (tested, test_subscriptions.py:283-331,381).
- Every billing write is scoped to the owning user_id with no cross-tenant leak, counts/metadata only (FR-22) — MET.
- Every external claim on the page is true (currency 'chosen at checkout', 'incl. GST', 'card never reaches our servers') — NOT met: GST is an unbacked label and 'chosen at checkout' is really a fixed static link.

**Findings:**
- **[critical/domain-truth]** The 'Pay in {currency}' button is a single static provider link shared by every paid plan, so the plan the user selects never reaches checkout. billing.html:52 sets pay_link purely from currency, and payment_link() (stripe_link.py:32) takes no plan/amount arg. Clicking 'Pay in USD' on Scale ($99) hits the same Stripe hosted page as Pro; provisioning then relies on Stripe metadata.plan which DEFAULTS to 'pro' (stripe_link.py:88). Failure: a Scale-intending buyer is charged/provisioned as Pro — paid-for tier != received tier.
  - evidence: `src/tokenops_cost_auditor/web/templates/app/billing.html:52`
- **[major/domain-truth]** Displayed launch/list price is structurally decoupled from the actual charge. launch_open() flips the shown price from launch to list in code the instant the cohort fills (plans.py:241-247), but the real charge is the static hosted link updated MANUALLY; the code comment itself admits a window where a subscriber pays the launch price against a list display. Failure: cohort fills, page shows $29 while the un-updated Stripe link still charges $19 (or the reverse after edits) — price shown != price charged, with nothing enforcing agreement.
  - evidence: `src/tokenops_cost_auditor/services/payments/plans.py:241`
- **[major/domain-truth]** India pricing shows a dollar figure that does not reconcile with the rupee it charges, and shows a HIGHER dollar price to India for the same tier. display() renders usd_india ($4.99/$9.99 Pro, $149 Scale) while billed_note discloses ₹499/₹999/₹14,999 (plans.py:68-89, config.py:158-161). ₹499 ~= $6 not $4.99; Scale is $149 to Indian viewers vs $99 globally for the identical plan. Failure: an enterprise buyer reads the dollar figure as the price and cannot reconcile it with either the global dollar price or the rupee charge.
  - evidence: `src/tokenops_cost_auditor/services/payments/plans.py:68`
- **[minor/domain-truth]** billed_note hardcodes 'incl. GST' (plans.py:89) but nothing in the slice computes, breaks out, or remits GST — it is a static label appended to a config rupee amount, with no tax breakup or GSTIN anywhere. Failure: customer is told '₹999/mo incl. GST' with no tax component calculated or invoiced; the claim is unverifiable from code and a compliance liability if the hosted link's amount is not actually GST-inclusive.
  - evidence: `src/tokenops_cost_auditor/services/payments/plans.py:89`
- **[minor/unhandled-state]** display() for INR uses usd_india and returns '—' when it is None (plans.py:72-77), while billed_note keys only on self.inr (plans.py:82-89) and still prints an INR charge line. Failure: a paid plan configured with inr set but usd_india unset (e.g. plan_team_usd_india -> 0/None) renders a self-contradicting price cell: '— ... Billed in India as ₹14,999/mo incl. GST'. Not triggered by current defaults but unguarded.
  - evidence: `src/tokenops_cost_auditor/services/payments/plans.py:73`
- **[minor/missing-test]** The inbound half is genuinely e2e-tested (webhook POST -> apply_event -> Subscription persisted at test_subscriptions.py:305-309, plus GET /billing render and 401 unauth), but no test binds the outbound Pay button to the correct plan/price — because with one static link per provider it cannot be enforced. Failure: a regression pointing every plan's button at the wrong single link, or hosted-link price drift, ships green since only display strings and the webhook lifecycle are asserted.
  - evidence: `src/tokenops_cost_auditor/web/templates/app/billing.html:52`

**Data safety:** Owner-scoped and safe. apply_event looks up/creates the user by normalized-lowercased email and keeps exactly one Subscription per user_id (subscriptions.py:139-149); grant_payment and claim_credit are scoped to user_id, with claim_credit using an atomic conditional UPDATE (base.py:37-66) that prevents two uploads double-spending one credit and cannot touch another user's row. cohort_used reads the append-only AuditLogEntry only to COUNT global launch slots (not tenant data), so no leak. FR-22 honored: Payment/WebhookEvent store amount/currency/ref/counts only, never prompt or completion text. Read-only-against-provider honored: adapters only HMAC-verify and JSON-parse inbound webhooks; no outbound provider API calls in this slice. One residual: a signature-valid webhook auto-creates a User+Subscription from arbitrary email (subscriptions.py:139-143), acceptable because the shared webhook secret authenticates the provider. No path found to corrupt, delete, or cross-leak another tenant's data.
