# PLAN-ORG — enterprise workspaces, members, RBAC, SSO

**Status: RULED (founder 2026-07-23, R-ORG — "proceed with both").** The
X-03 freeze is relaxed, bounded, for product governance only. This plan
breaks the enterprise org-management surface (the one part of a Sentry-
class settings tree that required a freeze change) into vertical slices.

## 0. The hard boundary this plan never crosses

Roles govern **who can see and do things IN OUR PRODUCT** — mint an ingest
key, open a report, change billing, revoke a source. Roles **never** touch
the customer's LLM traffic. X-01 (no proxy) and X-02 (no enforcement) stand
exactly as before. The audit **engine stays tenant-blind**: the tenancy
layer lives at the web + persistence boundary; `services/rules` and
`services/pricing` never learn what a workspace is (T-NFR-01 unaffected).
Single-tenant is the default — every existing user becomes a workspace of
one, no journey changes for them; organizations are opt-in.

## 1. The honest engineering reality

The app keys ownership on `user_id` today. Introducing a tenancy layer is
the largest architectural change since v1.0 — every owned table
(sources, ingest_keys, audits, subscriptions, saved_views, devices,
alert_rules, …) gains a `workspace_id`, and every read/write scopes to it.
The risk concentrates in **O-0**; the sequencing below delivers it as one
carefully-migrated slice so nothing after it is a big-bang rewrite.

## 2. Slices (each vertical per rule 9, gated per TE)

- **O-0 Workspace spine** (~3-4d, the load-bearing slice). A `Workspace`
  entity; a `WorkspaceMember` join (the minter is `owner`); backfill a
  personal workspace-of-one for every existing user; add `workspace_id`
  to every owned table (additive migration, backfilled from `user_id`'s
  workspace); scope every query. The audit engine is untouched — it still
  runs on rows, tenant-blind. DoD: every existing single-user journey
  byte-identical; the reachability + journey suites green under the new
  scoping; a second workspace's data is invisible to the first (the
  isolation test is the whole point).
  [DELIVERED 2026-07-24 — founder decision "Spine now, read-scope in O-1"
  (AskUserQuestion): O-0 ships the SPINE — Workspace + WorkspaceMember,
  migration 020 backfilling a workspace-of-one per user, `workspace_id` on
  the 10 directly-owned resource tables (audits, sources, ingest_keys,
  api_tokens, oauth_apps, saved_views, alert_rules, subscriptions,
  statements, devices), the write-path stamping it on creation, the
  Settings workspace surface (see + rename), and the isolation test. The
  40+ READ sites STAY user_id-scoped in O-0 — which is provably correct
  while 1 user = 1 workspace, so ZERO leak risk and O-0's DoD (B invisible
  to A) is met by the 1:1 invariant. The read re-scoping to workspace_id
  MOVES INTO O-1, where multi-membership is what makes it load-bearing;
  O-1 re-scopes reads with no new migration (the columns already exist and
  are populated). This is a bounded, safer sequencing of the same work,
  not a scope cut.]

- **O-1 Members + invites** (~2-3d). Invite by email (one-shot hashed
  code, the link-code grammar); a member joins a workspace; the Members
  page (Sentry's, honestly ours). Observe-only: a member sees the
  workspace's audits/reports. DoD: invite → accept → the invitee reaches
  the shared dashboard; revoke membership stops access; honest empty
  states. FIRST TASK (inherited from O-0): re-scope the 40+ read sites
  from `user_id` to `workspace_id` — the moment a second member exists,
  user-scoped reads would hide the workspace's data from them, so this is
  O-1's enabler. The columns already exist and are backfilled (O-0), so no
  migration; the S-6 ingest/read tokens also flip to workspace scope here
  (PLAN-SDK §3). The isolation test hardens from "1:1 correct" to
  "multi-member correct."

- **O-2 Roles (RBAC)** (~2-3d). `owner | admin | member | viewer` with a
  permission matrix over PRODUCT actions only (mint/revoke keys, manage
  billing, manage sources, view vs manage reports) — the matrix Sentry's
  General Settings exposes, minus anything touching traffic. Enforced at
  the route boundary; the engine never sees a role. DoD: each role's
  rendered surface is pinned (a viewer cannot mint a key; the control is
  absent, not just 403'd — the reachability law for permissions).

- **O-3 Enterprise SSO** (~3d). SAML/OIDC per workspace, on top of the
  existing individual federated sign-in (Google/MS/GitHub already ship).
  Org-enforced SSO (a workspace can require it); the Auth / Security &
  Privacy pages. DoD: an SSO-required workspace refuses password/magic-
  link for its members; the IdP round-trip journey walked end to end.

- **O-4 Workspace settings home** (~1-2d). Gather General · Members ·
  Auth · Audit Log (the workspace-scoped auditlog we already write) into
  one settings surface, the way Sentry's org settings are organized —
  an organizing surface over O-0..O-3, no new capability.

## 3. Interaction with the SDK platform

The ingest DSN already anticipated this (`/w/<workspace>` in PLAN-SDK §1).
Post-O-0, ingest keys and the read API tokens (S-6) become
workspace-scoped rather than user-scoped — a one-line change once the
spine exists. S-6 can ship BEFORE O-0 as personal tokens and gain
workspace scoping in O-0's migration.

## 4. Open questions for the founder

- Q1: Build order — O-0 first (unblocks all of it) after the current SDK
  slices (S-1), or interleave? Recommended: finish S-1, ship S-6, then
  O-0, so the tenancy migration lands once and both key types scope in it.
- Q2: SSO protocol priority — SAML (classic enterprise) vs OIDC (modern)
  first? Recommended OIDC first (reuses the federated-sign-in machinery),
  SAML second.
- Q3: Billing model per workspace — one subscription per workspace, or
  seat-based? (Affects O-0's subscription scoping.) Recommended: one
  subscription per workspace to start; seats later if asked.
