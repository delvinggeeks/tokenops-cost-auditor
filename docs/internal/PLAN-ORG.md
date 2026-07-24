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

- **O-1 Members + invites.** Observe-only tenancy: a member sees the
  workspace's audits/reports. Delivered in halves, then split into three
  member-facing vertical slices (founder 2026-07-24: "split ... concretely
  [into] vertical slices so we create new sessions for separate tasks with
  acceptance criteria and DoD for each"). Each slice below is ONE fresh
  session (K-3/TE-9), ships END-TO-END (R-VERTICAL: backend + UI + click path
  + journey test + ux gate + honest empty/error states), and gate-closes
  before the next. `active_workspace_id`, `set_active_workspace`,
  `list_memberships`, `WorkspaceInvite`, and billing-by-workspace already
  exist (O-1b backend, commit d52960e) — these slices are the reachable
  surfaces on top.

  - **[DONE] O-1a read re-scope** (commit d7a5c43, gated). Every display
    read scopes to `active_workspace_id` + `workspace_id`; S-6 tokens too.
  - **[DONE] O-1b backend foundation** (commit d52960e). Migration 021
    (`users.active_workspace_id`, `workspace_invites`, `workspace_id` on
    alert logs); switchable membership-validated resolver; billing
    inheritance (founder Q3 ruling: one sub per workspace, members inherit;
    visibility role-gated in O-2); alert-log member-visibility. All
    behavior-preserving under 1:1.

  ### O-1b-1 — Workspace switcher (the navigation spine) [~0.5-1 session]
  GOAL (journey): a user who belongs to more than one workspace can move
  between them, and always knows which one they are acting in.
  DESIGN/UI (mockup FIRST, ux gate): an "acting in: <workspace>" indicator
  in the app shell (topbar), and a switcher (dropdown or Settings→Workspace
  list) of the user's workspaces with their role; a solo user sees an honest
  "just your workspace — invite people to share it" (no fake affordance).
  BACKEND: POST `/settings/workspace/switch` → `repo.set_active_workspace`
  (already validates membership); render the current workspace from
  `active_workspace_id`; list via `repo.list_memberships`.
  REACHABILITY: the indicator is on every app page (shell); the switch
  control is one click from it.
  ACCEPTANCE CRITERIA: (1) the active-workspace name is visible on the app
  shell; (2) switching changes what EVERY read returns (dashboard, sources,
  runs, reports); (3) switching to a workspace the user is NOT a member of
  is refused and changes nothing; (4) a single-workspace user sees the
  honest solo state, no dead control; (5) reachable end to end by clicking.
  DoD: journey test seeds a user into two workspaces (membership rows
  directly) and walks switch → every surface flips; non-membership switch
  refused; ux gate on the mockup + wiring; suite green; gate round
  (ux + spec + cold + system-tester). DEPENDS ON: O-1b backend (done).
  SESSION START: "proceed O-1b-1 (workspace switcher)".

  ### O-1b-2 — Invite & accept (grow the workspace) [~1 session, the core]
  GOAL (journey): an owner invites a teammate by email; the teammate accepts
  and lands in the shared workspace, seeing the workspace's audits/dashboard.
  DESIGN/UI (mockup FIRST): a Members surface with an invite form (email +
  role=member) and a pending-invites list with honest states (pending /
  expired); the emailed accept link; an accept confirmation that drops the
  invitee INTO the shared workspace (auto-switch on accept, using O-1b-1's
  spine to move/return).
  BACKEND: POST `/settings/members/invite` — OWNER-ONLY, gated to the
  **Scale/"team" plan** (that plan was sold as multi-seat and this is what
  lets it deliver — see plans.py TEAM note), rate-limited (NFR-03/12
  pattern), mint a one-shot code (`WorkspaceInvite`, hashed via
  `credential_fingerprint`, shown once in the email), email the accept link.
  GET/POST `/invite/accept?code=` — require the logged-in user's email to
  MATCH the invite email (defense in depth), atomic single-use consume
  (UPDATE ... WHERE consumed_at IS NULL, the LinkCode grammar), add
  `WorkspaceMember(role="member")`, then `set_active_workspace` to the joined
  workspace.
  ACCEPTANCE CRITERIA: (1) invite is emailed, code stored only as a hash;
  (2) accept requires a matching email AND an unconsumed, unexpired code —
  wrong email / reused / expired all refused with honest messages; (3) on
  accept the user is a member and their active workspace is the shared one;
  (4) the invitee now sees the workspace's audits on the dashboard; (5)
  invite is owner-only + Scale-gated + rate-limited; (6) a non-member still
  sees nothing shared (isolation holds — hardens the test from 1:1 to
  multi-member).
  DoD: journey test walks owner-invite → invitee-accept → shared dashboard
  shows the owner's audits → isolation for a third party; adversarial cases
  (wrong email, reused code, expired) pinned; ux gate; suite green; gate
  round. DEPENDS ON: O-1b-1 (the switcher spine, so the invitee can
  navigate/return). SESSION START: "proceed O-1b-2 (invite & accept)".

  ### O-1b-3 — Members page & revoke (govern the workspace) [~0.5-1 session]
  GOAL (journey): an owner sees who is in the workspace and can remove them;
  a removed member loses access.
  DESIGN/UI (mockup FIRST): the full Members page under Settings — members
  list (email · role · joined), pending invites with resend/cancel, and a
  revoke control per member (owner-only, `data-confirm`); honest empty state
  ("just you so far — invite a teammate").
  BACKEND: POST `/settings/members/{id}/revoke` — OWNER-ONLY, deletes the
  `WorkspaceMember`; the switchable resolver already falls a revoked member
  back to their personal workspace on the next request (no extra work — pin
  it with a test). Invite resend (re-mint) / cancel (consume/expire).
  REACHABILITY: a "Members" entry in the Settings nav.
  ACCEPTANCE CRITERIA: (1) Members page reachable from Settings, lists
  members (role, joined) + pending invites; (2) owner revokes → that
  member's next request no longer sees the workspace (falls back to
  personal) → access stops; (3) mutations are owner-only — a plain member
  sees NO revoke/invite control (absent, not just 403 — the reachability law
  for permissions, foreshadowing O-2); (4) honest empty states; (5) resend
  and cancel pending invites work.
  DoD: journey test walks revoke → access stops; owner-only surface pinned;
  ux gate; suite green; gate round. Then update STATUS + docs/04-TRACEABILITY
  and O-1 closes. DEPENDS ON: O-1b-2 (members exist to govern). SESSION
  START: "proceed O-1b-3 (members page & revoke)".

  NOTE — deferred OUT of O-1 into O-2 (role-gated) or later, so no slice
  above silently owns them: billing VISIBILITY to non-owners (Payment stays
  user-scoped); every mutate a member might attempt beyond the above
  (revoke a source, mint a key, edit alert rules, purge) stays owner-scoped
  fail-closed until O-2 assigns roles.

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
