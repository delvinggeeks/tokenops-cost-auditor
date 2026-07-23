# PLAN-COPILOT — GitHub Copilot seat governance (WP-COPILOT-AGG)

**Status: AWAITING FOUNDER RULING (two real decisions below).** Scoped one
line in PLAN-TAAS §2 ("admin seat/usage export, T1-style upload first,
seat-waste findings"); this breaks it down and surfaces where it collides
with your own laws so you can rule before code.

## 0. What Copilot actually exposes (verified 2026-07-24)

GitHub Copilot Business/Enterprise is billed **per seat** ($19 / $39 per
user per month), not per token. Admin surfaces:
- `/orgs/{org}/copilot/billing/seats` — every billed seat, each with
  `assignee.login`, **`last_activity_at`**, `pending_cancellation`,
  `created_at`.
- `seat_breakdown`: total · active_this_cycle · **inactive_this_cycle** ·
  pending_invitation · pending_cancellation.
- Admins can download an **Activity report CSV**.

So the "waste" here is **idle seats** — licenses assigned to people who
haven't used Copilot in N days — not token inefficiency. It does NOT fit
the six token detectors; it's a different analysis.

## 1. Why this isn't just another connector

**(a) A different analysis kind.** Seat utilization, not token waste. The
finding is "N seats inactive ≥ D days → $X/mo recoverable by reclaiming
them," plus never-activated and pending-cancellation seats. None of the
six detectors apply.

**(b) A money figure the automated pricing gate can't verify.** R-AUTO-
PRICING's strict gate corroborates PER-TOKEN model rates against the
LiteLLM feed. Copilot's **per-seat** prices ($19/$39/mo) are SaaS
subscription prices — NOT in that feed, nothing to corroborate them
against automatically. So the seat-waste dollar figure sits outside the
no-human-gate machinery by construction.

**(c) X-02 stays intact.** "You have N idle seats" is OBSERVATION. We never
reclaim or enforce — the customer acts. Same observe-only line as the rest
of the product.

## 2. Decision 1 — where seat-waste lives

- **Option A (recommended): a new finding type in the existing report.**
  `d7_idle_seats` (a seat finding, not a token detector) runs on an
  uploaded Copilot seat file; it appears in the same report/explorer/runs
  as a ranked dollar line, labeled "seat governance" so it never reads as
  token waste. Minimal vertical slice; reuses the whole report shell.
- **Option B: a separate seat-governance surface.** Its own page/report.
  Bigger; arguably its own product. More honest separation, more build.

## 3. Decision 2 — how the seat $ figure is priced honestly

R-AUTO-PRICING can't cover per-seat SaaS prices. Choices:
- **Option P1 (recommended): report SEATS and last-activity as the hard
  fact; make the $ a stated, per-seat rate the CUSTOMER confirms** (default
  to GitHub's public $19/$39, shown as an editable assumption). The
  honesty: seat COUNTS are measured; the dollar rate is an input, labeled.
- **Option P2: a small separate "SaaS seat prices" verification** (a new
  source list for seat products) — heavier, and no clean independent feed
  exists the way LiteLLM covers token prices.

## 4. Proposed slice (once ruled)

Upload-first (no GitHub API dependency): a "Copilot seat export" tab on
Get-your-logs; parse the seats CSV/JSON (counts + last_activity, no
content — FR-22 trivially holds, it's seat metadata); the idle-seat
finding with its stated per-seat rate; the report/explorer surface;
honest coverage ("seat governance, not token audit"); journey test. A
GitHub-API connector is a later slice if you want live pull.

## 5. The ask

- Q1: Decision 1 — Option A (finding in the existing report) or B (separate
  surface)? Recommend A.
- Q2: Decision 2 — Option P1 (measured seats, customer-confirmed rate) or
  P2 (build seat-price verification)? Recommend P1.
- Q3: Upload-first now, GitHub-API connector later — agreed?
