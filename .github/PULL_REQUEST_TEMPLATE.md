# Milestone PR — reviewer checklist (REV-X + the standing laws)

## What ships
<!-- One paragraph: the slice, end to end. R-VERTICAL: backend + UI +
click path + journey test + honest states, in THIS PR or it doesn't merge. -->

## Gate verdicts
<!-- Paste TE-8 verdicts: vv / cold / spec / system-tester (+ ux when a
surface changed). FAILs must show the fix commit and the re-gate. -->

- [ ] vv-engineer:
- [ ] cold-reviewer:
- [ ] spec-guard:
- [ ] system-tester:
- [ ] ux-reviewer (surfaces only):

## The laws (check each honestly)

- [ ] **X-scope (REV-X)**: no live proxy/gateway, no enforcement, no
      multi-org RBAC/SSO, no LLM narrative, no SPA (X-01..X-05)
- [ ] **FR-22**: no prompt/completion text persisted anywhere; counts,
      ids and user-safe words only
- [ ] **Money law (rule 4 + R-AUTO-PRICING)**: pricing/estimator changes
      carry goldens + NOTES derivation in this PR, and
      `uv run python scripts/pricing_verify.py` exits 0
- [ ] **Traceability (rule 5)**: docs/04-TRACEABILITY.md updated in this PR
- [ ] **R-NAMING**: the full product name everywhere; no short name
- [ ] **Authorship**: commits by Lokesh Prasanna Kumar S only — no
      co-author trailers, no AI references in commit metadata
- [ ] **Reachability**: every new capability is click-reachable
      (TestDeclaredEqualsReachable green)

## Deploy notes
<!-- Migrations? .env keys? Runbook steps? CHANGELOG entry ready? -->
